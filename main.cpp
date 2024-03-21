#include <array>
#include <charconv>
#include <cstdio>
#include <ctime>
#include <lwip/mld6.h>
#include <lwip/sockets.h>
#include <lwip/tcpip.h>
#include <map>
#include <nlohmann/json.hpp>
#include <string>
#include <vector>
#include <ZeroTierSockets.h>

#define SIZE_NEEDED(gameDataField) PacketHeaderSize \
    + (reinterpret_cast<const uint8_t*>(&gameDataField) - reinterpret_cast<const uint8_t*>(gameData)) \
    + sizeof(gameDataField)

typedef std::vector<uint8_t> buffer_t;
typedef std::array<uint8_t, 16> address_t;

uint64_t net_id = 0xa84ac5c10a7ebb5f;
int default_port = 6112;

const uint8_t dvl_multicast_addr[16] = {
    // clang-format off
    0xff, 0x0e, 0xa8, 0xa9, 0xb6, 0x11, 0x61, 0xce,
    0x04, 0x12, 0xfd, 0x73, 0x37, 0x86, 0x6f, 0xb7,
    // clang-format on
};

void zt_ip6setup()
{
    ip6_addr_t mcaddr;
    memcpy(mcaddr.addr, dvl_multicast_addr, 16);
    mcaddr.zone = 0;
    LOCK_TCPIP_CORE();
    mld6_joingroup(IP6_ADDR_ANY6, &mcaddr);
    UNLOCK_TCPIP_CORE();
}

void set_reuseaddr(int fd)
{
    const int yes = 1;
    lwip_setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, (void*)&yes, sizeof(yes));
}

void set_nonblock(int fd)
{
    static_assert(O_NONBLOCK == 1, "O_NONBLOCK == 1 not satisfied");
    auto mode = lwip_fcntl(fd, F_GETFL, 0);
    mode |= O_NONBLOCK;
    lwip_fcntl(fd, F_SETFL, mode);
}

int fd_udp = -1;

void bring_network_online()
{
    struct sockaddr_in6 in6 {
    };
    in6.sin6_port = htons(default_port);
    in6.sin6_family = AF_INET6;
    in6.sin6_addr = in6addr_any;

    if(fd_udp == -1) {
        fd_udp = lwip_socket(AF_INET6, SOCK_DGRAM, 0);
        set_reuseaddr(fd_udp);
        auto ret = lwip_bind(fd_udp, (struct sockaddr*)&in6, sizeof(in6));
        if(ret < 0) {
            fprintf(stderr, "Error\n");
            exit(1);
        }
        set_nonblock(fd_udp);
        fprintf(stderr, "network_online\n");
    }
}

void print_ip6_addr(void* x)
{
    char ipstr[INET6_ADDRSTRLEN];
    auto* in = static_cast<sockaddr_in6*>(x);
    lwip_inet_ntop(AF_INET6, &(in->sin6_addr), ipstr, INET6_ADDRSTRLEN);
    fprintf(stderr, "ZeroTier: ZTS_EVENT_ADDR_NEW_IP6, addr=%s\n", ipstr);
}

bool zt_node_online = false;
bool zt_joined = false;
bool zt_network_ready = false;

static void Callback(void* ptr)
{
    zts_event_msg_t* msg = reinterpret_cast<zts_event_msg_t*>(ptr);
    if(msg->event_code == ZTS_EVENT_NODE_ONLINE) {
        fprintf(stderr, "ZeroTier: ZTS_EVENT_NODE_ONLINE, nodeId=%llx\n", (unsigned long long)msg->node->node_id);
        zt_node_online = true;
        if(!zt_joined) {
            zts_net_join(net_id);
            bring_network_online();
            zt_joined = true;
        }
    } else if(msg->event_code == ZTS_EVENT_NODE_OFFLINE) {
        fprintf(stderr, "ZeroTier: ZTS_EVENT_NODE_OFFLINE\n");
        zt_node_online = false;
    } else if(msg->event_code == ZTS_EVENT_NETWORK_READY_IP6) {
        fprintf(stderr, "ZeroTier: ZTS_EVENT_NETWORK_READY_IP6, networkId=%llx\n",
            (unsigned long long)msg->network->net_id);
        zt_ip6setup();
        zt_network_ready = true;
    } else if(msg->event_code == ZTS_EVENT_ADDR_ADDED_IP6) {
        print_ip6_addr(&(msg->addr->addr));
    } else if(msg->event_code == ZTS_EVENT_NODE_UP) {
        fprintf(stderr, "ZeroTier: ZTS_EVENT_NODE_UP\n");
    } else if(msg->event_code == ZTS_EVENT_NETWORK_OK) {
        fprintf(stderr, "ZeroTier: ZTS_EVENT_NETWORK_OK\n");
    } else if(msg->event_code == ZTS_EVENT_NETWORK_UPDATE) {
        fprintf(stderr, "ZeroTier: ZTS_EVENT_NETWORK_UPDATE\n");
    } else if(msg->event_code == ZTS_EVENT_PEER_DIRECT) {
        fprintf(stderr, "ZeroTier: ZTS_EVENT_PEER_DIRECT\n");
    } else if(msg->event_code == ZTS_EVENT_PEER_RELAY) {
        fprintf(stderr, "ZeroTier: ZTS_EVENT_PEER_RELAY\n");
    } else if(msg->event_code == ZTS_EVENT_PEER_PATH_DISCOVERED) {
        fprintf(stderr, "ZeroTier: ZTS_EVENT_PEER_PATH_DISCOVERED\n");
    } else if(msg->event_code == ZTS_EVENT_STORE_PLANET) {
        fprintf(stderr, "ZeroTier: ZTS_EVENT_STORE_PLANET\n");
    } else if(msg->event_code == ZTS_EVENT_STORE_IDENTITY_SECRET) {
        fprintf(stderr, "ZeroTier: ZTS_EVENT_STORE_IDENTITY_SECRET\n");
    } else if(msg->event_code == ZTS_EVENT_STORE_IDENTITY_PUBLIC) {
        fprintf(stderr, "ZeroTier: ZTS_EVENT_STORE_IDENTITY_PUBLIC\n");
    } else {
        fprintf(stderr, "callback %i\n", msg->event_code);
    }
}

void send_oob_mc(const buffer_t& data)
{
    struct sockaddr_in6 in6 {
    };
    in6.sin6_port = htons(default_port);
    in6.sin6_family = AF_INET6;
    std::copy(dvl_multicast_addr, dvl_multicast_addr + 16, in6.sin6_addr.s6_addr);
    lwip_sendto(fd_udp, data.data(), data.size(), 0, (const struct sockaddr*)&in6, sizeof(in6));
}

struct GameData {
    int32_t size;
    uint32_t seed;
    uint32_t type;
    uint8_t versionMajor;
    uint8_t versionMinor;
    uint8_t versionPatch;
    uint8_t difficulty;
    uint8_t tickRate;
    uint8_t runInTown;
    uint8_t theoQuest;
    uint8_t cowQuest;
    uint8_t friendlyFire;
    uint8_t fullQuests;
};

// GameInfo represents a value for json serialisation, the types chosen represent constraints of that
//  format and not expected values from DevilutionX
struct GameInfo {
    using json_string = std::string;
    using json_number = uint64_t;
    using json_boolean = bool;
    template <class T>
    using json_array = std::vector<T>;

    json_string id;
    json_string address;
    json_number seed;
    json_string type;
    json_string version;
    json_number difficulty;
    json_number tickRate;
    json_boolean runInTown;
    json_boolean theoQuest;
    json_boolean cowQuest;
    json_boolean friendlyFire;
    json_boolean fullQuests;
    json_array<json_string> players;
};

void to_json(nlohmann::json& j, const GameInfo& game)
{
    j = nlohmann::json {
        { "id", game.id },
        { "address", game.address },
        { "seed", game.seed },
        { "type", game.type },
        { "version", game.version },
        { "difficulty", game.difficulty },
        { "tick_rate", game.tickRate },
        { "run_in_town", game.runInTown },
        { "theo_quest", game.theoQuest },
        { "cow_quest", game.cowQuest },
        { "friendly_fire", game.friendlyFire },
        { "full_quests", game.fullQuests },
        { "players", game.players },
    };
}

bool recv(address_t& addr, buffer_t& data)
{
    unsigned char buf[65536];
    struct sockaddr_in6 in6 {
    };
    socklen_t addrlen = sizeof(in6);
    auto len = lwip_recvfrom(fd_udp, buf, sizeof(buf), 0, (struct sockaddr*)&in6, &addrlen);
    if(len < 0)
        return false;
    data.resize(len);
    memcpy(data.data(), buf, len);
    std::copy(in6.sin6_addr.s6_addr, in6.sin6_addr.s6_addr + 16, addr.begin());
    return true;
}

static constexpr uint8_t MaxPlayers = 4;
static constexpr uint8_t Host = 0xFE;
static constexpr uint8_t Broadcast = 0xFF;
static constexpr uint8_t InfoRequest = 0x21;
static constexpr uint8_t InfoReply = 0x22;

std::map<std::string, GameInfo> gameList;
constexpr size_t PlayerNameLength = 32;

std::string makeVersionString(const GameData& gameData)
{
    // each part can be at most 3 digits ("255"), plus the two separators, plus one for the road
    constexpr size_t MAX_VERSION_STR_LENGTH = 12;
    std::array<char, MAX_VERSION_STR_LENGTH> buffer {};
    auto end = buffer.data() + buffer.size();

    std::to_chars_result result = std::to_chars(buffer.data(), end, gameData.versionMajor);
    if(result.ec != std::errc()) {
        fprintf(stderr, std::make_error_code(result.ec).message().c_str());
        return {};
    }
    *result.ptr = '.';
    ++result.ptr;
    result = std::to_chars(result.ptr, end, gameData.versionMinor);
    if(result.ec != std::errc()) {
        fprintf(stderr, std::make_error_code(result.ec).message().c_str());
        return {};
    }
    *result.ptr = '.';
    ++result.ptr;
    result = std::to_chars(result.ptr, end, gameData.versionPatch);
    if(result.ec != std::errc()) {
        fprintf(stderr, std::make_error_code(result.ec).message().c_str());
        return {};
    }

    return std::string(buffer.data(), result.ptr);
}

void decode(const buffer_t& data, address_t sender)
{
    const size_t PacketHeaderSize = 3;
    if(data.size() < PacketHeaderSize)
        return;

    if(data[0] == InfoRequest) {
        return; // Ignore requests from other clients
    }

    if(data[0] != InfoReply || data[1] != Broadcast || data[2] != Host) {
        fprintf(stderr, "Unknown response\n");
        fprintf(stderr, "Type %02X\n", data[0]);
        fprintf(stderr, "src %02X\n", data[1]);
        fprintf(stderr, "dest %02X\n", data[2]);
        return;
    }

    const GameData* gameData = reinterpret_cast<const GameData*>(data.data() + PacketHeaderSize);
    if(data.size() < SIZE_NEEDED(gameData->size))
        return;
    const size_t neededSize = PacketHeaderSize + gameData->size + (PlayerNameLength * MaxPlayers);
    if(data.size() < neededSize)
        return;

    GameInfo game;

    const size_t gameNameSize = data.size() - neededSize;
    game.id.assign(reinterpret_cast<const char*>(data.data() + neededSize), gameNameSize);

    char ipstr[INET6_ADDRSTRLEN];
    if(lwip_inet_ntop(AF_INET6, sender.data(), ipstr, INET6_ADDRSTRLEN) == NULL)
        return;           // insufficient buffer, shouldn't be possible.
    game.address = ipstr; // lwip_inet_ntop returns a null terminated string so we don't need to use assign

    if(SIZE_NEEDED(gameData->seed) <= gameData->size)
        game.seed = gameData->seed;

    if(SIZE_NEEDED(gameData->type) <= gameData->size) {
        const char* type = reinterpret_cast<const char*>(&gameData->type);
        game.type.assign({ type[3], type[2], type[1], type[0] });
    }

    if(SIZE_NEEDED(gameData->versionPatch) <= gameData->size)
        game.version = makeVersionString(*gameData);
    if(SIZE_NEEDED(gameData->difficulty) <= gameData->size)
        game.difficulty = gameData->difficulty;
    if(SIZE_NEEDED(gameData->tickRate) <= gameData->size)
        game.tickRate = gameData->tickRate;
    if(SIZE_NEEDED(gameData->runInTown) <= gameData->size)
        game.runInTown = static_cast<bool>(gameData->runInTown);
    if(SIZE_NEEDED(gameData->theoQuest) <= gameData->size)
        game.theoQuest = static_cast<bool>(gameData->theoQuest);
    if(SIZE_NEEDED(gameData->cowQuest) <= gameData->size)
        game.cowQuest = static_cast<bool>(gameData->cowQuest);
    if(SIZE_NEEDED(gameData->friendlyFire) <= gameData->size)
        game.friendlyFire = static_cast<bool>(gameData->friendlyFire);
    if(SIZE_NEEDED(gameData->fullQuests) <= gameData->size)
        game.fullQuests = static_cast<bool>(gameData->fullQuests);

    for(size_t i = 0; i < MaxPlayers; i++) {
        std::string playerName;
        const char* playerNamePointer = (const char*)(data.data() + PacketHeaderSize + gameData->size + (i * PlayerNameLength));
        playerName.append(playerNamePointer, strnlen(playerNamePointer, PlayerNameLength));
        if(!playerName.empty())
            game.players.push_back(playerName);
    }

    gameList[game.id] = game;
}

int main(int argc, char* argv[])
{
    zts_init_from_storage("./zerotier");
    zts_init_set_event_handler(&Callback);
    zts_node_start();

    while(!zt_network_ready || !zt_node_online) {
        zts_util_delay(1000);
    }

    fprintf(stderr, "Sending multicast game info request\n");
    send_oob_mc({ InfoRequest, Broadcast, Host });

    address_t peer = {};
    buffer_t data;
    bool dataRecived = false;

    // Wait for peers for 5 seconds
    std::time_t result = std::time(nullptr);
    while(dataRecived || std::time(nullptr) - result < 5) {
        dataRecived = recv(peer, data);
        if(dataRecived) {
            decode(data, peer);
        }
        zts_util_delay(1000);
    }

    zts_node_stop();

    nlohmann::json root = nlohmann::json::array();
    for(const auto& game : gameList) {
        root.push_back(game.second);
    }
    printf(root.dump().c_str());

    return 0;
}

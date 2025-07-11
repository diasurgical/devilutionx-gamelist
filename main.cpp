#include <array>
#include <atomic>
#include <charconv>
#include <chrono>
#include <cstdio>
#include <lwip/mld6.h>
#include <lwip/prot/ethernet.h>
#include <lwip/prot/tcp.h>
#include <lwip/sockets.h>
#include <lwip/tcpip.h>
#include <map>
#include <mutex>
#include <nlohmann/json.hpp>
#include <string>
#include <vector>
#include <ZeroTierSockets.h>

#define SIZE_NEEDED(gameDataField) PacketHeaderSize \
    + (reinterpret_cast<const uint8_t*>(&gameDataField) - reinterpret_cast<const uint8_t*>(gameData)) \
    + sizeof(gameDataField)

typedef std::vector<uint8_t> buffer_t;
typedef std::array<uint8_t, 16> address_t;

struct PlayerIdentity {
    address_t address;
    std::string name;
};

uint64_t net_id = 0xa84ac5c10a7ebb5f;
int default_port = 6112;
int fd_udp = -1;

std::mutex player_identities_mutex;
std::vector<PlayerIdentity> player_identities;

const uint8_t dvl_multicast_addr[16] = {
    // clang-format off
    0xff, 0x0e, 0xa8, 0xa9, 0xb6, 0x11, 0x61, 0xce,
    0x04, 0x12, 0xfd, 0x73, 0x37, 0x86, 0x6f, 0xb7,
    // clang-format on
};

// ZTS_EVENT_NODE_UP:
void process_pt_message(const uint8_t* src, const uint8_t* pkt, size_t len)
{
    constexpr uint8_t CMD_ACK_PLRINFO = 0x02;
    constexpr uint8_t CMD_SEND_PLRINFO = 0x35;
    constexpr size_t TPktCheckOffset = 23;
    constexpr size_t TPktCmdOffset = 27;
    constexpr size_t TPktOffsetOffset = 28;
    constexpr size_t TPktPlayerNameOffset = 35;
    constexpr size_t TPktPlayerNameLength = 32;

    // Skip packet type and player IDs
    const uint8_t* tpkt = pkt + 3;
    const size_t tpktLen = len - 3;
    if(tpktLen < TPktPlayerNameOffset + TPktPlayerNameLength)
        return;

    // Sanity checks
    if(tpkt[TPktCheckOffset + 1] != 'i' || tpkt[TPktCheckOffset] != 'p')
        return;
    if(tpkt[TPktCmdOffset] != CMD_ACK_PLRINFO && tpkt[TPktCmdOffset] != CMD_SEND_PLRINFO)
        return;
    if(tpkt[TPktOffsetOffset] != 0 || tpkt[TPktOffsetOffset + 1] != 0)
        return;

    address_t playerAddress;
    memcpy(playerAddress.data(), src, playerAddress.size());
    const char* namePtr = reinterpret_cast<const char*>(tpkt + TPktPlayerNameOffset);
    const size_t nameLen = strnlen(namePtr, TPktPlayerNameLength);
    std::string playerName(namePtr, nameLen);

    std::lock_guard<std::mutex> lock(player_identities_mutex);
    player_identities.emplace_back(PlayerIdentity { playerAddress, playerName });
}

err_t ethernet_input(struct pbuf* p, struct netif* n)
{
    fprintf(stderr, "ZeroTier: Ethernet input not supported (netif=%c%c)\n", n->name[0], n->name[1]);
    return ERR_IF;
}

err_t ethip6_output(struct netif* n, struct pbuf* p, const ip6_addr_t* ip6addr)
{
    // Maximum MTU for ZeroTier virtual networks
    constexpr size_t ZT_MAX_MTU = 10000;
    uint8_t buf[ZT_MAX_MTU + 32];
    size_t len = 0;

    for(struct pbuf* q = p; q != nullptr; q = q->next) {
        memcpy(buf + len, q->payload, q->len);
        len += q->len;
    }

    size_t pos = 40;
    uint8_t protocol = buf[6];
    while(pos <= len) {
        switch(protocol) {
            case 0: // hop-by-hop options
            case 43: // routing
            case 60: // destination options
            case 135: // mobility options
                if ((pos + 8) > len)
                    return ERR_IF; // invalid!
                protocol = buf[pos];
                pos += ((unsigned int)buf[pos + 1] * 8) + 8;
                continue;
        }
        break;
    }

    // Only inspect non-empty TCP packets
    if(pos >= len || protocol != IPPROTO_TCP)
        return ERR_OK;

    const uint8_t* tcpData = buf + pos;
    const size_t tcpLen = len - pos;
    if(tcpLen < TCP_HLEN) return ERR_OK;
    const struct tcp_hdr* header = reinterpret_cast<const struct tcp_hdr*>(tcpData);

    // The game client communicates on TCP 6112
    const uint16_t sourcePort = lwip_ntohs(header->src);
    const uint16_t destinationPort = lwip_ntohs(header->dest);
    if(sourcePort != 6112 && destinationPort != 6112)
        return ERR_OK;

    const size_t headerLen = TCPH_HDRLEN_BYTES(header);
    if(tcpLen < headerLen) return ERR_OK;
    const uint8_t* payload = tcpData + headerLen;
    size_t payloadLen = tcpLen - headerLen;

    while(payloadLen >= sizeof(uint32_t)) {
        const uint32_t packetSize = *reinterpret_cast<const uint32_t*>(payload);
        if(packetSize <= 0) break;
        payload += sizeof(uint32_t);
        payloadLen -= sizeof(uint32_t);
        if(payloadLen < packetSize) break;

        constexpr uint8_t PT_MESSAGE = 0x01;
        const uint8_t packetType = payload[0];
        if(packetType == PT_MESSAGE)
            process_pt_message(buf + 8, payload, packetSize);
        payload += packetSize;
        payloadLen -= packetSize;
    }

    return ERR_OK;
}

err_t zts_lwip_eth_tx(struct netif* n, struct pbuf* p)
{
    fprintf(stderr, "ZeroTier: Link output not supported (netif=%c%c)\n", n->name[0], n->name[1]);
    return ERR_IF;
}

static err_t netif_init6(struct netif* n)
{
    if (n == nullptr) {
        return ERR_IF;
    }
    n->hwaddr[5] = 0xf3;
    n->hwaddr[4] = 0xaa;
    n->hwaddr[3] = 0x3d;
    n->hwaddr[2] = 0xf3;
    n->hwaddr[1] = 0xb2;
    n->hwaddr[0] = 0x8e;
    n->hwaddr_len = 6;
    n->name[0] = 'd';
    n->name[1] = 'x';
    n->linkoutput = zts_lwip_eth_tx;
    n->output_ip6 = ethip6_output;
    n->mtu = LWIP_MTU;
    n->flags = NETIF_FLAG_ETHERNET | NETIF_FLAG_LINK_UP | NETIF_FLAG_UP;
    return ERR_OK;
}

void create_network_interface(struct netif* n, ip6_addr_t* ip6)
{
    LOCK_TCPIP_CORE();
    netif_add(n, nullptr, nullptr, nullptr, nullptr, netif_init6, ethernet_input);
    n->ip6_autoconfig_enabled = 1;
    netif_create_ip6_linklocal_address(n, 1);
    netif_set_link_up(n);
    netif_set_up(n);
    netif_add_ip6_address(n, ip6, nullptr);
    UNLOCK_TCPIP_CORE();
}

void create_packet_sniffer()
{
    static struct netif n;
    ip6_addr_t ip;
    IP6_ADDR_PART(&ip, 0,
        0xfd,
        (net_id >> 56) & 0xff,
        (net_id >> 48) & 0xff,
        (net_id >> 40) & 0xff);
    IP6_ADDR_PART(&ip, 1,
        (net_id >> 32) & 0xff,
        (net_id >> 24) & 0xff,
        (net_id >> 16) & 0xff,
        (net_id >> 8) & 0xff);
    IP6_ADDR_PART(&ip, 2, net_id & 0xff, 0xdb, 0x07, 0x00);
    IP6_ADDR_PART(&ip, 3, 0x00, 0x00, 0x00, 0x01);
    create_network_interface(&n, &ip);
}

// ZTS_EVENT_NODE_ONLINE:
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
            fprintf(stderr, "ZeroTier: Error binding to UDP %d\n", default_port);
            exit(1);
        }
        set_nonblock(fd_udp);
        printf("ZeroTier: Receiving packets on UDP %d\n", default_port);
    }
}

// ZTS_EVENT_NETWORK_READY_IP6:
void zt_ip6setup()
{
    ip6_addr_t mcaddr;
    memcpy(mcaddr.addr, dvl_multicast_addr, 16);
    mcaddr.zone = 0;
    LOCK_TCPIP_CORE();
    mld6_joingroup(IP6_ADDR_ANY6, &mcaddr);
    UNLOCK_TCPIP_CORE();
}

// ZTS_EVENT_ADDR_ADDED_IP6:
void print_ip6_addr(void* x)
{
    char ipstr[INET6_ADDRSTRLEN];
    auto* in = static_cast<sockaddr_in6*>(x);
    lwip_inet_ntop(AF_INET6, &(in->sin6_addr), ipstr, INET6_ADDRSTRLEN);
    printf("ZeroTier: ZTS_EVENT_ADDR_NEW_IP6, addr=%s\n", ipstr);
}

std::atomic_bool zt_node_online(false);
std::atomic_bool zt_joined(false);
std::atomic_bool zt_network_ready(false);

using steady_time_t = std::chrono::time_point<std::chrono::steady_clock>;
std::atomic<steady_time_t> zt_last_peer_update;

//#define ZT_VERBOSE_LOGGING

#ifdef ZT_VERBOSE_LOGGING
const char* zt_event_to_string(int16_t event_code)
{
    switch(event_code) {
    case ZTS_EVENT_NODE_ONLINE: return "ZTS_EVENT_NODE_OFFLINE";
    case ZTS_EVENT_NODE_OFFLINE: return "ZTS_EVENT_NODE_OFFLINE";
    case ZTS_EVENT_NETWORK_READY_IP4: return "ZTS_EVENT_NETWORK_READY_IP4";
    case ZTS_EVENT_NETWORK_READY_IP6: return "ZTS_EVENT_NETWORK_READY_IP6";
    case ZTS_EVENT_ADDR_ADDED_IP4: return "ZTS_EVENT_ADDR_ADDED_IP4";
    case ZTS_EVENT_ADDR_ADDED_IP6: return "ZTS_EVENT_ADDR_ADDED_IP6";
    case ZTS_EVENT_NODE_UP: return "ZTS_EVENT_NODE_UP";
    case ZTS_EVENT_NETWORK_OK: return "ZTS_EVENT_NETWORK_OK";
    case ZTS_EVENT_NETWORK_UPDATE: return "ZTS_EVENT_NETWORK_UPDATE";
    case ZTS_EVENT_PEER_DIRECT: return "ZTS_EVENT_PEER_DIRECT";
    case ZTS_EVENT_PEER_RELAY: return "ZTS_EVENT_PEER_RELAY";
    case ZTS_EVENT_PEER_PATH_DISCOVERED: return "ZTS_EVENT_PEER_PATH_DISCOVERED";
    case ZTS_EVENT_PEER_PATH_DEAD: return "ZTS_EVENT_PEER_PATH_DEAD";
    case ZTS_EVENT_STORE_PLANET: return "ZTS_EVENT_STORE_PLANET";
    case ZTS_EVENT_STORE_IDENTITY_SECRET: return "ZTS_EVENT_STORE_IDENTITY_SECRET";
    case ZTS_EVENT_STORE_IDENTITY_PUBLIC: return "ZTS_EVENT_STORE_IDENTITY_PUBLIC";
    default: return nullptr;
    }
}

void log_zt_event(zts_event_msg_t* msg)
{
    const char* eventText = zt_event_to_string(msg->event_code);

    switch(msg->event_code) {
    // These get logged regardless of verbosity
    case ZTS_EVENT_NODE_ONLINE:
    case ZTS_EVENT_NODE_OFFLINE:
    case ZTS_EVENT_NETWORK_READY_IP6:
    case ZTS_EVENT_ADDR_ADDED_IP6:
        break;

    // These log peer IDs
    case ZTS_EVENT_PEER_DIRECT:
    case ZTS_EVENT_PEER_RELAY:
    case ZTS_EVENT_PEER_PATH_DISCOVERED:
    case ZTS_EVENT_PEER_PATH_DEAD:
        printf("ZeroTier: %s, peerId=%llx\n", eventText, msg->peer->peer_id);
        break;

    default:
        if (eventText != nullptr) {
            printf("ZeroTier: %s\n", eventText);
        } else {
            printf("ZeroTier: Unrecognized event code: %d\n", msg->event_code);
        }
        break;
    }
}
#endif

static void Callback(void* ptr)
{
    zts_event_msg_t* msg = reinterpret_cast<zts_event_msg_t*>(ptr);

    switch(msg->event_code) {
    case ZTS_EVENT_NODE_UP:
        create_packet_sniffer();
        break;

    case ZTS_EVENT_NODE_ONLINE:
        printf("ZeroTier: ZTS_EVENT_NODE_ONLINE, nodeId=%llx\n", (unsigned long long)msg->node->node_id);
        zt_node_online = true;
        if(!zt_joined) {
            zts_net_join(net_id);
            bring_network_online();
            zt_joined = true;
        }
        break;

    case ZTS_EVENT_NODE_OFFLINE:
        printf("ZeroTier: ZTS_EVENT_NODE_OFFLINE\n");
        zt_node_online = false;
        break;

    case ZTS_EVENT_NETWORK_READY_IP6:
        printf("ZeroTier: ZTS_EVENT_NETWORK_READY_IP6, networkId=%llx\n",
            (unsigned long long)msg->network->net_id);
        zt_ip6setup();
        zt_last_peer_update = std::chrono::steady_clock::now();
        zt_network_ready = true;
        break;

    case ZTS_EVENT_ADDR_ADDED_IP6:
        print_ip6_addr(&(msg->addr->addr));
        break;

    case ZTS_EVENT_PEER_DIRECT:
    case ZTS_EVENT_PEER_RELAY:
    case ZTS_EVENT_PEER_PATH_DISCOVERED:
        zt_last_peer_update = std::chrono::steady_clock::now();
        break;
    }

#ifdef ZT_VERBOSE_LOGGING
    log_zt_event(msg);
#endif
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

std::vector<PlayerIdentity> get_player_sightings()
{
    std::lock_guard<std::mutex> lock(player_identities_mutex);
    std::vector<PlayerIdentity> playerSightings = player_identities;
    player_identities.clear();
    return playerSightings;
}

constexpr uint8_t MaxPlayers = 4;
constexpr uint8_t Host = 0xFE;
constexpr uint8_t Broadcast = 0xFF;
constexpr uint8_t InfoRequest = 0x21;
constexpr uint8_t InfoReply = 0x22;
constexpr size_t PlayerNameLength = 32;

std::string makeVersionString(const GameData& gameData)
{
    // each part can be at most 3 digits ("255"), plus the two separators, plus one for the road
    constexpr size_t MAX_VERSION_STR_LENGTH = 12;
    std::array<char, MAX_VERSION_STR_LENGTH> buffer {};
    auto end = buffer.data() + buffer.size();

    std::to_chars_result result = std::to_chars(buffer.data(), end, gameData.versionMajor);
    if(result.ec != std::errc()) {
        fprintf(stderr, "ZeroTier: Error parsing major version number. %s\n", std::make_error_code(result.ec).message().c_str());
        return {};
    }
    *result.ptr = '.';
    ++result.ptr;
    result = std::to_chars(result.ptr, end, gameData.versionMinor);
    if(result.ec != std::errc()) {
        fprintf(stderr, "ZeroTier: Error parsing minor version number. %s\n", std::make_error_code(result.ec).message().c_str());
        return {};
    }
    *result.ptr = '.';
    ++result.ptr;
    result = std::to_chars(result.ptr, end, gameData.versionPatch);
    if(result.ec != std::errc()) {
        fprintf(stderr, "ZeroTier: Error parsing patch version number. %s\n", std::make_error_code(result.ec).message().c_str());
        return {};
    }

    return std::string(buffer.data(), result.ptr);
}

bool decode(GameInfo& game, const buffer_t& data, address_t sender)
{
    const size_t PacketHeaderSize = 3;
    if(data.size() < PacketHeaderSize)
        return false;

    if(data[0] == InfoRequest) {
        return false; // Ignore requests from other clients
    }

    if(data[0] != InfoReply || data[1] != Broadcast || data[2] != Host) {
        const uint8_t* member = sender.data() + sender.size() - 5;
        fprintf(stderr, "ZeroTier: Unknown response (sender=%02X%02X%02X%02X%02X, type=%02X, src=%02X, dest=%02X)\n",
            member[0], member[1], member[2], member[3], member[4], data[0], data[1], data[2]);
        return false;
    }

    const GameData* gameData = reinterpret_cast<const GameData*>(data.data() + PacketHeaderSize);
    if(data.size() < SIZE_NEEDED(gameData->size))
        return false;
    const size_t neededSize = PacketHeaderSize + gameData->size + (PlayerNameLength * MaxPlayers);
    if(data.size() < neededSize)
        return false;

    const size_t gameNameSize = data.size() - neededSize;
    game.id.assign(reinterpret_cast<const char*>(data.data() + neededSize), gameNameSize);

    char ipstr[INET6_ADDRSTRLEN];
    if(lwip_inet_ntop(AF_INET6, sender.data(), ipstr, INET6_ADDRSTRLEN) == NULL)
        return false;     // insufficient buffer, shouldn't be possible.
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

    return true;
}

bool zt_peers_ready()
{
    const steady_time_t now = std::chrono::steady_clock::now();
    const steady_time_t peerUpdate = zt_last_peer_update;
    const steady_time_t::duration diff = now - peerUpdate;
    return diff >= std::chrono::seconds(5);
}

int main(int argc, char* argv[])
{
    const char* gameFilePath = "gamelist.json";
    if (argc > 1) {
        gameFilePath = argv[1];
    }

    zts_init_from_storage("./zerotier");
    zts_init_set_event_handler(&Callback);
    zts_node_start();

    while(!zt_network_ready || !zt_node_online || !zt_peers_ready()) {
        zts_util_delay(500);
    }

    std::map<std::string, GameInfo> gameList;
    std::size_t totalReplies = 0;
    std::size_t totalSightings = 0;

    printf("ZeroTier: Sending multicast game info request\n");
    send_oob_mc({ InfoRequest, Broadcast, Host });
    steady_time_t lastInfoRequest = std::chrono::steady_clock::now();

    while(true) {
        const steady_time_t now = std::chrono::steady_clock::now();
        const steady_time_t::duration diff = now - lastInfoRequest;
        if(diff >= std::chrono::seconds(60)) {
            printf("ZeroTier: Sending multicast game info request\n");
            printf("ZeroTier: Total replies received so far: %zu\n", totalReplies);
            printf("ZeroTier: Total player sightings so far: %zu\n", totalSightings);
            if(!gameList.empty()) {
                fprintf(stderr, "ZeroTier: Holding %zu games since last request! Is discord_bot running?\n", gameList.size());
            }
            send_oob_mc({ InfoRequest, Broadcast, Host });
            lastInfoRequest = now;
        }

        address_t peer = {};
        buffer_t data;
        while(recv(peer, data)) {
            GameInfo game;
            if (decode(game, data, peer)) {
                gameList[game.id] = game;
                totalReplies++;
            }
        }

        std::vector<PlayerIdentity> sightingList = get_player_sightings();
        totalSightings += sightingList.size();

        if(!gameList.empty() || !sightingList.empty()) {
            FILE* gameFile = fopen(gameFilePath, "wbx");
            if(gameFile != nullptr) {
                nlohmann::json games = nlohmann::json::array();
                for(const auto& game : gameList) {
                    games.push_back(game.second);
                }

                nlohmann::json sightings = nlohmann::json::array();
                for(const auto& sighting : sightingList) {
                    char ipstr[INET6_ADDRSTRLEN];
                    if(lwip_inet_ntop(AF_INET6, sighting.address.data(), ipstr, INET6_ADDRSTRLEN) == NULL)
                        continue;     // insufficient buffer, shouldn't be possible.
                    sightings.push_back(nlohmann::json {
                        { "address", std::string(ipstr) },
                        { "name", sighting.name }
                    });
                }

                nlohmann::json root = nlohmann::json {
                    { "games", games },
                    { "player_sightings", sightings }
                };

                std::string text = root.dump();
                std::fwrite(text.data(), sizeof(char), text.size(), gameFile);
                std::fclose(gameFile);
                gameList.clear();
            }
        }

        zts_util_delay(5000);
    }

    return 0;
}

include(FetchContent)

FetchContent_Declare(json
	URL https://github.com/nlohmann/json/releases/download/v3.12.0/json.tar.xz
	URL_HASH SHA256=42f6e95cad6ec532fd372391373363b62a14af6d771056dbfc86160e6dfff7aa
)
FetchContent_MakeAvailable(json)
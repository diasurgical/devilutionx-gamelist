#!/bin/bash
trap ':' SIGINT

rm -f gamelist.json
python3 discord_bot.py &
./devilutionx-gamelist &

while ! wait
do
  kill -TERM $(jobs -p)
done

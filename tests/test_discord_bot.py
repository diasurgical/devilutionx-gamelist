import pathlib
import pytest
from discord_bot import (
    escape_discord_formatting_characters,
    format_game_message,
    format_status_message,
    format_time_delta,
    any_player_name_is_invalid,
    any_player_name_contains_a_banned_word,
    config,
)


class TestEscapeDiscordFormattingCharacters:
    def test_escapes_asterisks(self) -> None:
        assert escape_discord_formatting_characters("*bold*") == "\\*bold\\*"

    def test_escapes_underscores(self) -> None:
        assert escape_discord_formatting_characters("_italic_") == "\\_italic\\_"

    def test_escapes_tildes(self) -> None:
        assert escape_discord_formatting_characters("~strike~") == "\\~strike\\~"

    def test_escapes_backticks(self) -> None:
        assert escape_discord_formatting_characters("`code`") == "\\`code\\`"

    def test_escapes_pipes(self) -> None:
        assert escape_discord_formatting_characters("||spoiler||") == "\\|\\|spoiler\\|\\|"

    def test_escapes_multiple_characters(self) -> None:
        result = escape_discord_formatting_characters("*_~`|#@")
        assert result == "\\*\\_\\~\\`\\|\\#\\@"

    def test_plain_text_unchanged(self) -> None:
        assert escape_discord_formatting_characters("hello world") == "hello world"


class TestFormatTimeDelta:
    def test_one_minute(self) -> None:
        assert format_time_delta(1) == "1 minute"

    def test_few_minutes(self) -> None:
        assert format_time_delta(5) == "5 minutes"

    def test_59_minutes(self) -> None:
        assert format_time_delta(59) == "59 minutes"

    def test_one_hour(self) -> None:
        assert format_time_delta(60) == "1 hour"

    def test_one_hour_and_minutes(self) -> None:
        assert format_time_delta(75) == "1 hour and 15 minutes"

    def test_two_hours(self) -> None:
        assert format_time_delta(120) == "2 hours"

    def test_multiple_hours_and_minutes(self) -> None:
        assert format_time_delta(150) == "2 hours and 30 minutes"


class TestFormatStatusMessage:
    def test_singular_game(self) -> None:
        result = format_status_message(1)
        assert result == "There is currently **1** public game."

    def test_plural_games(self) -> None:
        result = format_status_message(5)
        assert result == "There are currently **5** public games."

    def test_zero_games(self) -> None:
        result = format_status_message(0)
        assert result == "There are currently **0** public games."


class TestFormatGameMessage:
    def test_basic_game(self) -> None:
        game = {
            "id": "testgame",
            "type": "DRTL",
            "version": "1.5.0",
            "tick_rate": 20,
            "difficulty": 0,
            "run_in_town": False,
            "full_quests": False,
            "theo_quest": False,
            "cow_quest": False,
            "friendly_fire": False,
            "players": ["Player1"],
            "timestamp": 1700000000,
        }
        result = format_game_message(game)
        assert "**TESTGAME**" in result
        assert "Normal" in result
        assert "Player1" in result

    def test_ended_game_strikethrough(self) -> None:
        game = {
            "id": "testgame",
            "type": "DRTL",
            "version": "1.5.0",
            "tick_rate": 20,
            "difficulty": 0,
            "run_in_town": False,
            "full_quests": False,
            "theo_quest": False,
            "cow_quest": False,
            "friendly_fire": False,
            "players": ["Player1"],
            "timestamp": 1700000000,
            "ended": 1700003600,
            "first_seen": 1700000000,
        }
        result = format_game_message(game)
        assert "~~TESTGAME~~" in result
        assert "Ended after:" in result

    def test_hellfire_game(self) -> None:
        game = {
            "id": "hfgame",
            "type": "HRTL",
            "version": "1.5.0",
            "tick_rate": 20,
            "difficulty": 1,
            "run_in_town": False,
            "full_quests": False,
            "theo_quest": False,
            "cow_quest": False,
            "friendly_fire": False,
            "players": ["Player1"],
            "timestamp": 1700000000,
        }
        result = format_game_message(game)
        assert "hellfire" in result
        assert "Nightmare" in result

    def test_hell_difficulty(self) -> None:
        game = {
            "id": "hellgame",
            "type": "DRTL",
            "version": "1.5.0",
            "tick_rate": 20,
            "difficulty": 2,
            "run_in_town": False,
            "full_quests": False,
            "theo_quest": False,
            "cow_quest": False,
            "friendly_fire": False,
            "players": ["Player1"],
            "timestamp": 1700000000,
        }
        result = format_game_message(game)
        assert "Hell" in result

    def test_game_with_attributes(self) -> None:
        game = {
            "id": "attrsgame",
            "type": "HRTL",
            "version": "1.5.0",
            "tick_rate": 20,
            "difficulty": 0,
            "run_in_town": True,
            "full_quests": True,
            "theo_quest": True,
            "cow_quest": True,
            "friendly_fire": True,
            "players": ["Player1"],
            "timestamp": 1700000000,
        }
        result = format_game_message(game)
        assert "Run in Town" in result
        assert "Quests" in result
        assert "Theo Quest" in result
        assert "Cow Quest" in result
        assert "Friendly Fire" in result

    def test_tick_rate_fast_pre_160(self) -> None:
        game = {
            "id": "fastgame",
            "type": "DRTL",
            "version": "1.5.0",
            "tick_rate": 30,
            "difficulty": 0,
            "run_in_town": False,
            "full_quests": False,
            "theo_quest": False,
            "cow_quest": False,
            "friendly_fire": False,
            "players": ["Player1"],
            "timestamp": 1700000000,
        }
        result = format_game_message(game)
        assert "Fast" in result

    def test_tick_rate_fast_post_160(self) -> None:
        game = {
            "id": "fastgame",
            "type": "DRTL",
            "version": "1.6.0",
            "tick_rate": 25,
            "difficulty": 0,
            "run_in_town": False,
            "full_quests": False,
            "theo_quest": False,
            "cow_quest": False,
            "friendly_fire": False,
            "players": ["Player1"],
            "timestamp": 1700000000,
        }
        result = format_game_message(game)
        assert "Fast" in result

    def test_multiple_players(self) -> None:
        game = {
            "id": "multigame",
            "type": "DRTL",
            "version": "1.5.0",
            "tick_rate": 20,
            "difficulty": 0,
            "run_in_town": False,
            "full_quests": False,
            "theo_quest": False,
            "cow_quest": False,
            "friendly_fire": False,
            "players": ["Alice", "Bob", "Charlie"],
            "timestamp": 1700000000,
        }
        result = format_game_message(game)
        assert "Alice" in result
        assert "Bob" in result
        assert "Charlie" in result


class TestAnyPlayerNameIsInvalid:
    def test_valid_names(self) -> None:
        assert any_player_name_is_invalid(["Alice", "Bob123"]) is False

    def test_name_with_comma(self) -> None:
        assert any_player_name_is_invalid(["Ali,ce"]) is True

    def test_name_with_space(self) -> None:
        assert any_player_name_is_invalid(["Ali ce"]) is True

    def test_name_with_angle_brackets(self) -> None:
        assert any_player_name_is_invalid(["<script>"]) is True

    def test_name_with_percent(self) -> None:
        assert any_player_name_is_invalid(["100%"]) is True

    def test_name_with_ampersand(self) -> None:
        assert any_player_name_is_invalid(["Tom&Jerry"]) is True

    def test_name_with_backslash(self) -> None:
        assert any_player_name_is_invalid(["path\\name"]) is True

    def test_name_with_quotes(self) -> None:
        assert any_player_name_is_invalid(['say"hi"']) is True

    def test_name_with_question_mark(self) -> None:
        assert any_player_name_is_invalid(["who?"]) is True

    def test_name_with_asterisk(self) -> None:
        assert any_player_name_is_invalid(["star*"]) is True

    def test_name_with_hash(self) -> None:
        assert any_player_name_is_invalid(["hash#tag"]) is True

    def test_name_with_slash(self) -> None:
        assert any_player_name_is_invalid(["path/name"]) is True

    def test_name_with_colon(self) -> None:
        assert any_player_name_is_invalid(["time:now"]) is True

    def test_name_with_control_character(self) -> None:
        assert any_player_name_is_invalid(["test\x00"]) is True

    def test_name_with_non_ascii(self) -> None:
        assert any_player_name_is_invalid(["tëst"]) is True

    def test_mixed_valid_invalid(self) -> None:
        assert any_player_name_is_invalid(["ValidName", "Invalid Name"]) is True


class TestAnyPlayerNameContainsBannedWord:
    def test_no_banlist_file(self, tmp_path: pathlib.Path) -> None:
        original = config["banlist_file"]
        config["banlist_file"] = str(tmp_path / "nonexistent")
        result = any_player_name_contains_a_banned_word(["Player"])
        config["banlist_file"] = original
        assert result is False

    def test_empty_banlist(self, tmp_path: pathlib.Path) -> None:
        banlist = tmp_path / "banlist"
        banlist.write_text("")
        original = config["banlist_file"]
        config["banlist_file"] = str(banlist)
        result = any_player_name_contains_a_banned_word(["Player"])
        config["banlist_file"] = original
        assert result is False

    def test_banned_word_found(self, tmp_path: pathlib.Path) -> None:
        banlist = tmp_path / "banlist"
        banlist.write_text("badword\n")
        original = config["banlist_file"]
        config["banlist_file"] = str(banlist)
        result = any_player_name_contains_a_banned_word(["xbadwordx"])
        config["banlist_file"] = original
        assert result is True

    def test_banned_word_case_insensitive(self, tmp_path: pathlib.Path) -> None:
        banlist = tmp_path / "banlist"
        banlist.write_text("BADWORD\n")
        original = config["banlist_file"]
        config["banlist_file"] = str(banlist)
        result = any_player_name_contains_a_banned_word(["badword"])
        config["banlist_file"] = original
        assert result is True

    def test_no_banned_word(self, tmp_path: pathlib.Path) -> None:
        banlist = tmp_path / "banlist"
        banlist.write_text("badword\n")
        original = config["banlist_file"]
        config["banlist_file"] = str(banlist)
        result = any_player_name_contains_a_banned_word(["goodplayer"])
        config["banlist_file"] = original
        assert result is False

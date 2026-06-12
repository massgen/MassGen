"""Tests for the declarative permission rule layer (Antigravity action(target))."""

import pytest

from massgen.permissions.rules import PermissionRuleSet, classify_action_target


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def test_parse_action_target():
    rs = PermissionRuleSet(allow=["command(git status)"])
    r = rs.allow_rules[0]
    assert r.action == "command"
    assert r.pattern == "git status"


def test_parse_wildcards():
    rs = PermissionRuleSet(deny=["*(*)"])
    assert rs.deny_rules[0].action == "*"
    assert rs.deny_rules[0].pattern == "*"


def test_bare_action_means_any_target():
    rs = PermissionRuleSet(ask=["read_url"])
    assert rs.ask_rules[0].action == "read_url"
    assert rs.ask_rules[0].pattern == "*"


# --------------------------------------------------------------------------- #
# tool/args → (action, target)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "tool,args,action,target",
    [
        ("mcp__command_line__execute_command", {"command": "git status"}, "command", "git status"),
        ("write_file", {"path": "src/a.py"}, "write_file", "src/a.py"),
        ("mcp__filesystem__edit_file", {"path": "src/a.py"}, "write_file", "src/a.py"),
        ("delete_file", {"path": "x"}, "write_file", "x"),
        ("read_file", {"path": "README.md"}, "read_file", "README.md"),
        ("WebFetch", {"url": "https://x.com/y"}, "read_url", "https://x.com/y"),
        ("mcp__linear__create_issue", {"title": "t"}, "mcp", "linear/create_issue"),
    ],
)
def test_classify_action_target(tool, args, action, target):
    assert classify_action_target(tool, args) == (action, target)


# --------------------------------------------------------------------------- #
# Evaluation precedence: deny > allow > ask > (None → fall to risk)
# --------------------------------------------------------------------------- #
def test_deny_wins_over_allow():
    rs = PermissionRuleSet(deny=["command(rm *)"], allow=["command(*)"])
    assert rs.evaluate("execute_command", {"command": "rm file.txt"}) == "deny"


def test_allow_matches():
    rs = PermissionRuleSet(allow=["command(git status)"])
    assert rs.evaluate("execute_command", {"command": "git status"}) == "allow"
    # not an exact glob match → no rule
    assert rs.evaluate("execute_command", {"command": "git status -s"}) is None


def test_ask_matches():
    rs = PermissionRuleSet(ask=["read_url(*)"])
    assert rs.evaluate("WebFetch", {"url": "https://x"}) == "ask"


def test_no_match_returns_none():
    rs = PermissionRuleSet(allow=["command(git status)"])
    assert rs.evaluate("execute_command", {"command": "python x.py"}) is None


def test_path_globs():
    rs = PermissionRuleSet(deny=["write_file(/etc/**)"], allow=["write_file(./**)"])
    assert rs.evaluate("write_file", {"path": "/etc/passwd"}) == "deny"
    assert rs.evaluate("write_file", {"path": "./src/a.py"}) == "allow"


def test_mcp_glob():
    rs = PermissionRuleSet(allow=["mcp(linear/*)"])
    assert rs.evaluate("mcp__linear__create_issue", {}) == "allow"
    assert rs.evaluate("mcp__github__create_pr", {}) is None


def test_command_match_is_case_sensitive():
    rs = PermissionRuleSet(allow=["command(git status)"])
    assert rs.evaluate("execute_command", {"command": "GIT STATUS"}) is None


def test_wildcard_action_matches_anything():
    rs = PermissionRuleSet(deny=["*(*secret*)"])
    assert rs.evaluate("write_file", {"path": "/x/secret.txt"}) == "deny"
    assert rs.evaluate("execute_command", {"command": "cat secret"}) == "deny"


def test_merge_scopes_deny_wins_across():
    # project scope allows; managed scope denies → deny wins across scopes.
    project = PermissionRuleSet(allow=["command(*)"])
    managed = PermissionRuleSet(deny=["command(curl *)"])
    merged = PermissionRuleSet.merge([managed, project])
    assert merged.evaluate("execute_command", {"command": "curl evil"}) == "deny"
    assert merged.evaluate("execute_command", {"command": "ls"}) == "allow"


# --------------------------------------------------------------------------- #
# Role presets (per-agent scoping)
# --------------------------------------------------------------------------- #
def test_role_read_only_denies_writes_and_shell_allows_reads():
    from massgen.permissions.rules import role_rule_set

    rs = role_rule_set("read-only")
    assert rs.evaluate("write_file", {"path": "x"}) == "deny"
    assert rs.evaluate("execute_command", {"command": "ls"}) == "deny"  # no shell
    assert rs.evaluate("read_file", {"path": "x"}) == "allow"
    assert rs.evaluate("WebFetch", {"url": "x"}) == "ask"


def test_role_researcher_is_alias_for_read_only():
    from massgen.permissions.rules import role_rule_set

    assert role_rule_set("researcher").evaluate("write_file", {"path": "x"}) == "deny"


def test_role_read_write_is_empty():
    from massgen.permissions.rules import role_rule_set

    assert role_rule_set("read-write").is_empty


def test_role_unknown_or_none_returns_none():
    from massgen.permissions.rules import role_rule_set

    assert role_rule_set(None) is None
    assert role_rule_set("bogus") is None


def test_role_deny_beats_user_allow():
    from massgen.permissions.rules import role_rule_set

    role = role_rule_set("read-only")
    user = PermissionRuleSet(allow=["write_file(./out.txt)"])
    merged = PermissionRuleSet.merge([role, user])
    # read-only role's write-deny cannot be loosened by a per-agent allow.
    assert merged.evaluate("write_file", {"path": "./out.txt"}) == "deny"

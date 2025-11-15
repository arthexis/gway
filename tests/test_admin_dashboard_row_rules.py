from __future__ import annotations

from projects import admin_dashboard


class DummyGroup:
    def __init__(self, name: str):
        self.name = name


class DummyGroups:
    def __init__(self, *groups: DummyGroup):
        self._groups = list(groups)

    def all(self):
        return list(self._groups)


class DummyUser:
    def __init__(
        self,
        username: str,
        *,
        roles=None,
        groups=None,
        is_active: bool = True,
        is_superuser: bool = False,
        is_staff: bool = False,
        email: str | None = "",
    ):
        self.username = username
        self.roles = roles
        self.groups = groups
        self.is_active = is_active
        self.is_superuser = is_superuser
        self.is_staff = is_staff
        self.email = email


def test_admin_with_watchtower_role_must_be_inactive():
    watchtower_group = DummyGroup("WatchTower Operators")
    admin_user = DummyUser(
        "admin",
        groups=DummyGroups(watchtower_group),
        is_staff=True,
        is_active=True,
    )

    result = admin_dashboard.check_user_row_rules(users=[admin_user])

    assert not result["ok"]
    assert result["errors"] is not None
    codes = {error["code"] for error in result["errors"]}
    assert "admin_watchtower_inactive" in codes


def test_superuser_requires_email():
    superuser = DummyUser("root", is_superuser=True, email=" ")

    result = admin_dashboard.check_user_row_rules(users=[superuser])

    assert not result["ok"]
    assert result["errors"] is not None
    codes = {error["code"] for error in result["errors"]}
    assert "superuser_email_required" in codes


def test_rules_pass_when_conditions_met():
    admin_user = DummyUser("admin", roles=["operator"], is_staff=True)
    superuser = DummyUser("root", is_superuser=True, email="root@example.com")

    result = admin_dashboard.check_user_row_rules(users=[admin_user, superuser])

    assert result["ok"]
    assert result["errors"] is None
    assert result["checked_users"] == 2
    assert result["superusers"] == 1


def test_fetch_users_from_model_when_not_supplied():
    admin_user = DummyUser("admin", is_staff=True, roles=["operator"], is_active=True)
    superuser = DummyUser("root", is_superuser=True, email="root@example.com")

    class DummyManager:
        def __init__(self, objects):
            self._objects = list(objects)

        def all(self):
            return list(self._objects)

    class DummyModel:
        objects = DummyManager([admin_user, superuser])

    result = admin_dashboard.check_user_row_rules(user_model=DummyModel)

    assert result["ok"]
    assert result["errors"] is None
    assert result["checked_users"] == 2

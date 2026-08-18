"""
Role hierarchy helpers.

Canonical order (highest first):
  admin (5) > staff (4) > terminal (3) > teacher (2) > student (1) > pending (0)

Clerk provides identity only. Roles live on people.User and are changed by admins.
"""

ROLE_RANK = {
    'pending': 0,
    'student': 1,
    'teacher': 2,
    'terminal': 3,
    'staff': 4,
    'admin': 5,
}

# Roles that may operate the staff dashboard this cycle
OPERATIONAL_ROLES = frozenset({'admin', 'staff'})
CHECKIN_ROLES = frozenset({'admin', 'staff', 'terminal'})


def is_active_account(user) -> bool:
    """Signed-in Django row that is not deactivated. Anonymous is never active."""
    return bool(
        user
        and getattr(user, 'is_authenticated', False)
        and getattr(user, 'is_active', False)
    )


def role_rank(user) -> int:
    if not is_active_account(user):
        return -1
    return ROLE_RANK.get(getattr(user, 'role', None), -1)


def is_admin(user) -> bool:
    return role_rank(user) >= ROLE_RANK['admin']


def is_staff_or_above(user) -> bool:
    return role_rank(user) >= ROLE_RANK['staff']


def is_terminal_or_above(user) -> bool:
    return role_rank(user) >= ROLE_RANK['terminal']


def is_teacher_or_above(user) -> bool:
    return role_rank(user) >= ROLE_RANK['teacher']


def is_at_least(user, role: str) -> bool:
    return role_rank(user) >= ROLE_RANK[role]


def can_check_in(user) -> bool:
    return is_active_account(user) and getattr(user, 'role', None) in CHECKIN_ROLES

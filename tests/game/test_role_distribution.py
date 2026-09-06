"""Role distribution invariants.

Every composition must hand out exactly one role per player — a mis-sized
entry used to silently drop roles via zip() truncation (a 9-player game
could start without a Doctor).
"""

from apps.game.engine.roles.distributor import (
    ROLE_COMPOSITIONS,
    RoleDistributor,
)


def test_every_composition_matches_its_player_count():
    for count, composition in ROLE_COMPOSITIONS.items():
        assert len(composition) == count, (
            f'composition for {count} players has {len(composition)} roles'
        )


def test_nine_player_game_includes_doctor_and_three_mafia():
    player_ids = list(range(1, 10))
    players = RoleDistributor.distribute(player_ids)

    assert len(players) == 9
    role_codes = [p.role.code for p in players]
    assert 'doctor' in role_codes
    mafia_roles = [p for p in players if p.role.role_type.value == 'mafia']
    assert len(mafia_roles) == 3
    assert len(set(player_ids)) == 9

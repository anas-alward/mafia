from enum import StrEnum


class PlayerStatus(StrEnum):
    ALIVE = 'alive'
    DEAD = 'dead'


class ActionType(StrEnum):
    KILL = 'kill'
    REVENGE = 'revenge'
    VOTE = 'vote'
    HEAL = 'heal'
    DETECT = 'detect'
    SHOOT = 'shoot'
    SILENCE = 'silence'
    LYNCH = 'lynch'


class Phase(StrEnum):
    DAY = 'day'
    NIGHT = 'night'
    VOTE_RESULT = 'vote_result'


class SignalAudience(StrEnum):
    """Who receives an action's tile signal (transient animation + border)."""

    NONE = 'none'              # no signal is emitted for this action
    EVERYONE = 'everyone'      # all players in the game
    ACTOR_ONLY = 'actor_only'  # verification: echoed to the actor alone
    MAFIA_ONLY = 'mafia_only'  # alive mafia members, actor identity hidden


from dataclasses import dataclass


@dataclass
class ActionConfig:
    action_type: ActionType
    required: bool
    priority: int | None = None

    def to_dict(self) -> dict:
        return {
            'action_type': self.action_type.value,
            'required': self.required,
            'priority': self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ActionConfig':
        return cls(
            action_type=ActionType(data['action_type']),
            required=data['required'],
            priority=data.get('priority'),
        )


@dataclass(frozen=True)
class ActionDefinition:
    """Presentation + signal policy for one ActionType.

    Single source of truth for how an action looks and who its tile signal
    reaches — the equivalent of the role registry, but data-driven.
    `color` / `bg` / `border_color` carry frontend-ready CSS values (CSS
    variables or hex literals); `icon` is a Lucide icon name.
    """

    action_type: ActionType
    label: str
    icon: str
    color: str
    bg: str
    border_color: str
    signal_audience: SignalAudience
    signal_actor_visible: bool

    def to_dict(self) -> dict:
        return {
            'action_type': self.action_type.value,
            'label': self.label,
            'icon': self.icon,
            'color': self.color,
            'bg': self.bg,
            'border_color': self.border_color,
            'signal_audience': self.signal_audience.value,
            'signal_actor_visible': self.signal_actor_visible,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ActionDefinition':
        return cls(
            action_type=ActionType(data['action_type']),
            label=data['label'],
            icon=data['icon'],
            color=data['color'],
            bg=data['bg'],
            border_color=data['border_color'],
            signal_audience=SignalAudience(data['signal_audience']),
            signal_actor_visible=data['signal_actor_visible'],
        )


ACTION_REGISTRY: dict[ActionType, ActionDefinition] = {
    ActionType.VOTE: ActionDefinition(
        action_type=ActionType.VOTE,
        label='Vote',
        icon='vote',
        color='var(--game-gold)',
        bg='rgba(237, 184, 58, 0.22)',
        border_color='var(--game-gold)',
        signal_audience=SignalAudience.EVERYONE,
        signal_actor_visible=True,
    ),
    ActionType.KILL: ActionDefinition(
        action_type=ActionType.KILL,
        label='Eliminated',
        icon='skull',
        color='var(--game-crimson)',
        bg='rgba(240, 96, 107, 0.30)',
        border_color='var(--game-crimson)',
        signal_audience=SignalAudience.MAFIA_ONLY,
        signal_actor_visible=False,
    ),
    ActionType.REVENGE: ActionDefinition(
        action_type=ActionType.REVENGE,
        label='Eliminated',
        icon='bomb',
        color='var(--game-crimson)',
        bg='rgba(240, 96, 107, 0.30)',
        border_color='var(--game-crimson)',
        signal_audience=SignalAudience.EVERYONE,
        signal_actor_visible=True,
    ),
    ActionType.HEAL: ActionDefinition(
        action_type=ActionType.HEAL,
        label='Healed',
        icon='heart-pulse',
        color='var(--game-mint)',
        bg='rgba(77, 232, 160, 0.24)',
        border_color='var(--game-mint)',
        signal_audience=SignalAudience.ACTOR_ONLY,
        signal_actor_visible=False,
    ),
    ActionType.DETECT: ActionDefinition(
        action_type=ActionType.DETECT,
        label='Detect',
        icon='search',
        color='var(--game-periwinkle)',
        bg='rgba(143, 160, 245, 0.24)',
        border_color='var(--game-periwinkle)',
        signal_audience=SignalAudience.NONE,
        signal_actor_visible=False,
    ),
    ActionType.SHOOT: ActionDefinition(
        action_type=ActionType.SHOOT,
        label='Eliminated',
        icon='crosshair',
        color='#F5925E',
        bg='rgba(240, 96, 107, 0.30)',
        border_color='#F5925E',
        signal_audience=SignalAudience.ACTOR_ONLY,
        signal_actor_visible=False,
    ),
    ActionType.SILENCE: ActionDefinition(
        action_type=ActionType.SILENCE,
        label='Silenced',
        icon='mic-off',
        color='#C49EF0',
        bg='rgba(196, 158, 240, 0.24)',
        border_color='#C49EF0',
        signal_audience=SignalAudience.ACTOR_ONLY,
        signal_actor_visible=False,
    ),
    ActionType.LYNCH: ActionDefinition(
        action_type=ActionType.LYNCH,
        label='Eliminated',
        icon='skull',
        color='var(--game-crimson)',
        bg='rgba(240, 96, 107, 0.30)',
        border_color='var(--game-crimson)',
        signal_audience=SignalAudience.NONE,
        signal_actor_visible=False,
    ),
}


def public_action_registry() -> list[dict]:
    """Serialize the registry for clients (e.g. game state payloads)."""
    return [definition.to_dict() for definition in ACTION_REGISTRY.values()]

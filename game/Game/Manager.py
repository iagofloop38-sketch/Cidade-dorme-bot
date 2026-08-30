"""Máquina de estados de uma partida de Cidade Dorme."""

from dataclasses import dataclass, field
from enum import Enum, auto

from .roles import Role, ROLE_TEAM, TEAM_LOBOS, TEAM_VILA, get_role_distribution


class Phase(Enum):
    LOBBY = auto()
    NIGHT = auto()
    DAY_DISCUSSION = auto()
    DAY_VOTE = auto()
    ENDED = auto()


@dataclass
class Player:
    user_id: int
    display_name: str
    role: Role | None = None
    alive: bool = True
    lover_id: int | None = None


@dataclass
class Game:
    guild_id: int
    channel_id: int
    host_id: int
    phase: Phase = Phase.LOBBY
    night_number: int = 0
    night_step: int = 1  # 1 = ação geral (lobos/vidente/cupido), 2 = turno da bruxa
    players: dict[int, Player] = field(default_factory=dict)

    # ações coletadas durante a noite atual
    wolf_votes: dict[int, int] = field(default_factory=dict)   # lobo_id -> alvo_id
    seer_target: int | None = None
    witch_heal_used: bool = False
    witch_poison_used: bool = False
    witch_heal_this_night: bool = False
    witch_poison_target: int | None = None
    cupid_done: bool = False

    # votação do dia
    day_votes: dict[int, int] = field(default_factory=dict)  # eleitor_id -> alvo_id

    # pendências
    pending_hunter_revenge: int | None = None  # user_id do caçador que precisa vingar

    log: list[str] = field(default_factory=list)

    # ---------- lobby ----------

    def add_player(self, user_id: int, display_name: str) -> bool:
        if self.phase != Phase.LOBBY:
            return False
        if user_id in self.players:
            return False
        self.players[user_id] = Player(user_id=user_id, display_name=display_name)
        return True

    def remove_player(self, user_id: int) -> bool:
        if self.phase != Phase.LOBBY:
            return False
        return self.players.pop(user_id, None) is not None

    def start_game(self) -> None:
        if len(self.players) < 5:
            raise ValueError("São necessários pelo menos 5 jogadores para iniciar.")
        roles = get_role_distribution(len(self.players))
        for player, role in zip(self.players.values(), roles):
            player.role = role
        self.phase = Phase.NIGHT
        self.night_number = 1

    # ---------- helpers ----------

    def alive_players(self) -> list[Player]:
        return [p for p in self.players.values() if p.alive]

    def players_with_role(self, role: Role) -> list[Player]:
        return [p for p in self.alive_players() if p.role == role]

    def get_player(self, user_id: int) -> Player | None:
        return self.players.get(user_id)

    def is_first_night(self) -> bool:
        return self.night_number == 1

    # ---------- ações noturnas ----------

    def record_wolf_vote(self, wolf_id: int, target_id: int) -> None:
        self.wolf_votes[wolf_id] = target_id

    def record_seer_target(self, target_id: int) -> None:
        self.seer_target = target_id

    def record_witch_heal(self) -> None:
        self.witch_heal_used = True
        self.witch_heal_this_night = True

    def record_witch_poison(self, target_id: int) -> None:
        self.witch_poison_used = True
        self.witch_poison_target = target_id

    def record_cupid(self, id1: int, id2: int) -> None:
        p1, p2 = self.players[id1], self.players[id2]
        p1.lover_id = id2
        p2.lover_id = id1
        self.cupid_done = True

    def wolf_kill_target(self) -> int | None:
        """Alvo mais votado pelos lobos (empate = None, ninguém morre)."""
        if not self.wolf_votes:
            return None
        counts: dict[int, int] = {}
        for target in self.wolf_votes.values():
            counts[target] = counts.get(target, 0) + 1
        max_votes = max(counts.values())
        top = [t for t, c in counts.items() if c == max_votes]
        return top[0] if len(top) == 1 else None

    def resolve_night(self) -> dict:
        """Processa a noite e retorna um resumo com quem morreu."""
        deaths: list[int] = []

        target = self.wolf_kill_target()
        if target is not None and not self.witch_heal_this_night:
            deaths.append(target)

        if self.witch_poison_target is not None:
            deaths.append(self.witch_poison_target)

        # casal apaixonado: se um morre, o outro morre junto
        extra_deaths = []
        for d in deaths:
            player = self.players.get(d)
            if player and player.lover_id and player.lover_id not in deaths:
                extra_deaths.append(player.lover_id)
        deaths.extend(extra_deaths)

        deaths = list(dict.fromkeys(deaths))  # remove duplicados, mantém ordem

        hunter_pending = None
        for d in deaths:
            player = self.players.get(d)
            if player:
                player.alive = False
                if player.role == Role.CACADOR:
                    hunter_pending = player.user_id

        self.pending_hunter_revenge = hunter_pending

        # reset das ações da noite
        self.wolf_votes = {}
        self.seer_target = None
        self.witch_heal_this_night = False
        self.witch_poison_target = None

        self.phase = Phase.DAY_DISCUSSION
        return {"deaths": deaths, "hunter_pending": hunter_pending}

    def apply_hunter_revenge(self, target_id: int) -> None:
        player = self.players.get(target_id)
        if player:
            player.alive = False
        self.pending_hunter_revenge = None

    # ---------- votação do dia ----------

    def start_day_vote(self) -> None:
        self.phase = Phase.DAY_VOTE
        self.day_votes = {}

    def record_day_vote(self, voter_id: int, target_id: int) -> None:
        self.day_votes[voter_id] = target_id

    def resolve_day_vote(self) -> dict:
        counts: dict[int, int] = {}
        for target in self.day_votes.values():
            counts[target] = counts.get(target, 0) + 1

        lynched = None
        if counts:
            max_votes = max(counts.values())
            top = [t for t, c in counts.items() if c == max_votes]
            if len(top) == 1:
                lynched = top[0]

        hunter_pending = None
        extra_deaths = []
        if lynched is not None:
            player = self.players.get(lynched)
            if player:
                player.alive = False
                if player.role == Role.CACADOR:
                    hunter_pending = player.user_id
                if player.lover_id and self.players.get(player.lover_id) and self.players[player.lover_id].alive:
                    self.players[player.lover_id].alive = False
                    extra_deaths.append(player.lover_id)

        self.pending_hunter_revenge = hunter_pending
        self.day_votes = {}
        self.night_number += 1
        self.phase = Phase.NIGHT

        return {"lynched": lynched, "extra_deaths": extra_deaths, "hunter_pending": hunter_pending}

    # ---------- condição de vitória ----------

    def check_win(self) -> str | None:
        alive = self.alive_players()
        wolves = [p for p in alive if p.role == Role.LOBISOMEM]
        villagers = [p for p in alive if p.role != Role.LOBISOMEM]

        if not wolves:
            return TEAM_VILA
        if len(wolves) >= len(villagers):
            return TEAM_LOBOS
        return None

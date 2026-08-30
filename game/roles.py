"""Definições dos papéis (roles) do jogo Cidade Dorme."""

from enum import Enum
import random


class Role(str, Enum):
    LOBISOMEM = "Lobisomem"
    ALDEAO = "Aldeão"
    VIDENTE = "Vidente"
    BRUXA = "Bruxa"
    CACADOR = "Caçador"
    CUPIDO = "Cupido"


TEAM_LOBOS = "lobos"
TEAM_VILA = "vila"

ROLE_TEAM = {
    Role.LOBISOMEM: TEAM_LOBOS,
    Role.ALDEAO: TEAM_VILA,
    Role.VIDENTE: TEAM_VILA,
    Role.BRUXA: TEAM_VILA,
    Role.CACADOR: TEAM_VILA,
    Role.CUPIDO: TEAM_VILA,
}

ROLE_DESCRIPTIONS = {
    Role.LOBISOMEM: (
        "🐺 **Lobisomem**\n"
        "Toda noite, você e os outros lobos escolhem um jogador para devorar. "
        "Durante o dia, finja ser um aldeão inocente.\n"
        "Use `/matar @jogador` na sua DM durante a noite."
    ),
    Role.ALDEAO: (
        "👤 **Aldeão**\n"
        "Você não tem poderes especiais. Sua missão é descobrir quem são os "
        "lobisomens e eliminá-los nas votações durante o dia."
    ),
    Role.VIDENTE: (
        "🔮 **Vidente**\n"
        "Toda noite você pode investigar um jogador e descobrir seu papel.\n"
        "Use `/investigar @jogador` na sua DM durante a noite."
    ),
    Role.BRUXA: (
        "🧪 **Bruxa**\n"
        "Você tem duas poções, cada uma usável apenas uma vez no jogo:\n"
        "• Poção de cura: salva a vítima dos lobos (`/salvar`)\n"
        "• Poção de veneno: mata um jogador à sua escolha (`/envenenar @jogador`)\n"
        "Você fica sabendo quem os lobos atacaram antes de decidir."
    ),
    Role.CACADOR: (
        "🏹 **Caçador**\n"
        "Se você morrer (de noite ou linchado de dia), pode atirar em alguém "
        "imediatamente, matando essa pessoa também.\n"
        "Use `/vingar @jogador` quando notificado da sua morte."
    ),
    Role.CUPIDO: (
        "💘 **Cupido**\n"
        "Somente na primeira noite, você escolhe dois jogadores (pode incluir "
        "você mesmo) para se tornarem o Casal Apaixonado. Se um deles morrer, "
        "o outro morre de tristeza junto — mesmo que sejam de times opostos.\n"
        "Use `/flechar @jogador1 @jogador2` na primeira noite."
    ),
}


def get_role_distribution(num_players: int) -> list[Role]:
    """Monta a lista de papéis para N jogadores, respeitando o pacote completo."""
    if num_players < 5:
        raise ValueError("São necessários pelo menos 5 jogadores.")

    # número de lobisomens: ~1 a cada 4 jogadores, mínimo 1
    num_lobos = max(1, num_players // 4)

    roles = [Role.LOBISOMEM] * num_lobos

    special_roles = [Role.VIDENTE, Role.BRUXA, Role.CACADOR, Role.CUPIDO]
    remaining_slots = num_players - num_lobos

    for role in special_roles:
        if remaining_slots <= 0:
            break
        roles.append(role)
        remaining_slots -= 1

    # preenche o resto com aldeões
    roles.extend([Role.ALDEAO] * remaining_slots)

    random.shuffle(roles)
    return roles

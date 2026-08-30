import discord
from discord import app_commands
from discord.ext import commands

from game.manager import Game, Phase
from game.roles import Role, ROLE_DESCRIPTIONS, TEAM_LOBOS, TEAM_VILA


class CidadeDormeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # uma partida ativa por canal
        self.games: dict[int, Game] = {}

    # ---------- helpers ----------

    def find_game_by_channel(self, channel_id: int) -> Game | None:
        return self.games.get(channel_id)

    def find_game_by_player(self, user_id: int) -> Game | None:
        for game in self.games.values():
            if user_id in game.players:
                return game
        return None

    async def dm(self, user_id: int, content: str) -> None:
        try:
            user = await self.bot.fetch_user(user_id)
            await user.send(content)
        except discord.Forbidden:
            pass

    async def announce_night_start(self, game: Game) -> None:
        alive = game.alive_players()
        wolves = game.players_with_role(Role.LOBISOMEM)
        wolf_names = ", ".join(p.display_name for p in wolves)

        for player in alive:
            if player.role == Role.LOBISOMEM:
                others = ", ".join(
                    f"{p.display_name}" for p in alive if p.role != Role.LOBISOMEM
                )
                await self.dm(
                    player.user_id,
                    f"🌙 **Noite {game.night_number}**\n"
                    f"Seus companheiros lobos: {wolf_names}\n"
                    f"Alvos possíveis: {others}\n"
                    f"Use `/matar` para escolher a vítima desta noite.",
                )
            elif player.role == Role.VIDENTE:
                await self.dm(
                    player.user_id,
                    f"🌙 **Noite {game.night_number}**\n"
                    f"Use `/investigar` para descobrir o papel de alguém.",
                )
            elif player.role == Role.CUPIDO and game.is_first_night() and not game.cupid_done:
                await self.dm(
                    player.user_id,
                    "💘 É a primeira noite! Use `/flechar` para escolher o Casal Apaixonado "
                    "(pode incluir você mesmo).",
                )
            elif player.role == Role.BRUXA:
                potions = []
                if not game.witch_heal_used:
                    potions.append("cura")
                if not game.witch_poison_used:
                    potions.append("veneno")
                if potions:
                    await self.dm(
                        player.user_id,
                        f"🌙 **Noite {game.night_number}**\n"
                        f"Poções disponíveis: {', '.join(potions)}.\n"
                        f"Aguarde o anúncio do alvo dos lobos antes de decidir "
                        f"(o host avisará quando for sua vez).",
                    )

        channel = self.bot.get_channel(game.channel_id)
        if channel:
            await channel.send(
                f"🌙 A cidade dorme... (Noite {game.night_number}). "
                f"Os jogadores com poderes receberam instruções na DM. "
                f"O host deve usar `/avancar` quando todos tiverem agido."
            )

    async def notify_witch_phase(self, game: Game) -> None:
        witches = game.players_with_role(Role.BRUXA)
        target_id = game.wolf_kill_target()
        target_name = "ninguém (empate)" if target_id is None else game.players[target_id].display_name
        for witch in witches:
            msg = f"🧪 Os lobos escolheram atacar: **{target_name}**.\n"
            if not game.witch_heal_used:
                msg += "Use `/salvar` para curar a vítima. "
            if not game.witch_poison_used:
                msg += "Use `/envenenar @jogador` para matar alguém com veneno."
            if game.witch_heal_used and game.witch_poison_used:
                msg = "🧪 Você já usou as duas poções. Nada a fazer esta noite."
            await self.dm(witch.user_id, msg)

    async def announce_deaths(self, channel: discord.abc.Messageable, deaths: list[int], game: Game) -> None:
        if not deaths:
            await channel.send("☀️ O dia amanhece e, surpreendentemente, ninguém morreu esta noite.")
            return
        names = [game.players[d].display_name for d in deaths if d in game.players]
        lines = "\n".join(f"💀 **{n}**" for n in names)
        await channel.send(f"☀️ O dia amanhece. Os seguintes jogadores morreram:\n{lines}")

    async def maybe_end_game(self, game: Game, channel: discord.abc.Messageable) -> bool:
        winner = game.check_win()
        if winner is None:
            return False
        game.phase = Phase.ENDED
        team_name = "🐺 Lobisomens" if winner == TEAM_LOBOS else "👤 Vila"
        reveal = "\n".join(
            f"{p.display_name} — {p.role.value}" for p in game.players.values()
        )
        await channel.send(f"🏆 **Fim de jogo! Vitória: {team_name}**\n\n**Papéis revelados:**\n{reveal}")
        del self.games[game.channel_id]
        return True

    # ---------- comandos de lobby ----------

    @app_commands.command(name="criar_partida", description="Cria uma nova partida de Cidade Dorme neste canal")
    async def criar_partida(self, interaction: discord.Interaction):
        if interaction.channel_id in self.games:
            await interaction.response.send_message("Já existe uma partida ativa neste canal.", ephemeral=True)
            return
        game = Game(guild_id=interaction.guild_id, channel_id=interaction.channel_id, host_id=interaction.user.id)
        self.games[interaction.channel_id] = game
        game.add_player(interaction.user.id, interaction.user.display_name)
        await interaction.response.send_message(
            f"🌆 Partida de **Cidade Dorme** criada por {interaction.user.mention}!\n"
            f"Use `/entrar` para participar e `/iniciar` (host) quando tiver pelo menos 5 jogadores."
        )

    @app_commands.command(name="entrar", description="Entra na partida do canal atual")
    async def entrar(self, interaction: discord.Interaction):
        game = self.find_game_by_channel(interaction.channel_id)
        if not game:
            await interaction.response.send_message("Não há partida neste canal. Use `/criar_partida`.", ephemeral=True)
            return
        if not game.add_player(interaction.user.id, interaction.user.display_name):
            await interaction.response.send_message("Você já está na partida ou ela já começou.", ephemeral=True)
            return
        await interaction.response.send_message(f"✅ {interaction.user.mention} entrou na partida! ({len(game.players)} jogadores)")

    @app_commands.command(name="sair", description="Sai da partida do canal atual (só antes de começar)")
    async def sair(self, interaction: discord.Interaction):
        game = self.find_game_by_channel(interaction.channel_id)
        if not game or not game.remove_player(interaction.user.id):
            await interaction.response.send_message("Você não está na partida ou ela já começou.", ephemeral=True)
            return
        await interaction.response.send_message(f"👋 {interaction.user.mention} saiu da partida.")

    @app_commands.command(name="jogadores", description="Lista jogadores da partida atual")
    async def jogadores(self, interaction: discord.Interaction):
        game = self.find_game_by_channel(interaction.channel_id)
        if not game:
            await interaction.response.send_message("Não há partida neste canal.", ephemeral=True)
            return
        if game.phase == Phase.LOBBY:
            names = ", ".join(p.display_name for p in game.players.values())
            await interaction.response.send_message(f"👥 Jogadores ({len(game.players)}): {names}")
        else:
            alive = ", ".join(p.display_name for p in game.alive_players())
            dead = ", ".join(p.display_name for p in game.players.values() if not p.alive)
            msg = f"👥 Vivos: {alive or '-'}"
            if dead:
                msg += f"\n💀 Mortos: {dead}"
            await interaction.response.send_message(msg)

    @app_commands.command(name="iniciar", description="Inicia a partida (somente o host)")
    async def iniciar(self, interaction: discord.Interaction):
        game = self.find_game_by_channel(interaction.channel_id)
        if not game:
            await interaction.response.send_message("Não há partida neste canal.", ephemeral=True)
            return
        if interaction.user.id != game.host_id:
            await interaction.response.send_message("Só o host pode iniciar a partida.", ephemeral=True)
            return
        try:
            game.start_game()
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        await interaction.response.send_message("🎬 A partida começou! Os papéis foram enviados por DM.")
        for player in game.players.values():
            desc = ROLE_DESCRIPTIONS[player.role]
            await self.dm(player.user_id, f"Seu papel nesta partida é:\n\n{desc}")

        await self.announce_night_start(game)

    @app_commands.command(name="encerrar", description="Encerra a partida à força (somente o host)")
    async def encerrar(self, interaction: discord.Interaction):
        game = self.find_game_by_channel(interaction.channel_id)
        if not game:
            await interaction.response.send_message("Não há partida neste canal.", ephemeral=True)
            return
        if interaction.user.id != game.host_id:
            await interaction.response.send_message("Só o host pode encerrar a partida.", ephemeral=True)
            return
        del self.games[interaction.channel_id]
        await interaction.response.send_message("🛑 Partida encerrada pelo host.")

    # ---------- avanço de fase (host) ----------

    @app_commands.command(name="avancar", description="Avança a fase da partida (somente o host)")
    async def avancar(self, interaction: discord.Interaction):
        game = self.find_game_by_channel(interaction.channel_id)
        if not game:
            await interaction.response.send_message("Não há partida neste canal.", ephemeral=True)
            return
        if interaction.user.id != game.host_id:
            await interaction.response.send_message("Só o host pode avançar a fase.", ephemeral=True)
            return

        channel = interaction.channel

        if game.phase == Phase.NIGHT:
            if game.night_step == 1:
                game.night_step = 2
                await self.notify_witch_phase(game)
                await interaction.response.send_message(
                    "🧪 Turno da Bruxa liberado. Use `/avancar` de novo quando ela (e os demais) tiverem agido."
                )
                return
            else:
                result = game.resolve_night()
                await interaction.response.send_message("☀️ Resolvendo a noite...")
                await self.announce_deaths(channel, result["deaths"], game)
                if result["hunter_pending"]:
                    name = game.players[result["hunter_pending"]].display_name
                    await channel.send(f"🏹 {name} era o Caçador! Ele pode usar `/vingar` na DM antes do dia continuar.")
                    await self.dm(result["hunter_pending"], "🏹 Você morreu! Use `/vingar @jogador` para atirar em alguém antes de partir.")
                game.night_step = 1
                if await self.maybe_end_game(game, channel):
                    return
                await channel.send("💬 Discussão livre. Quando terminarem, o host usa `/avancar` para abrir a votação.")

        elif game.phase == Phase.DAY_DISCUSSION:
            if game.pending_hunter_revenge:
                await interaction.response.send_message(
                    "⏳ Ainda aguardando a vingança do Caçador antes de votar.", ephemeral=True
                )
                return
            game.start_day_vote()
            names = ", ".join(p.display_name for p in game.alive_players())
            await interaction.response.send_message(f"🗳️ Votação aberta! Use `/votar @jogador`.\nVivos: {names}")

        elif game.phase == Phase.DAY_VOTE:
            result = game.resolve_day_vote()
            if result["lynched"] is None:
                await interaction.response.send_message("⚖️ A votação empatou, ninguém foi linchado hoje.")
            else:
                name = game.players[result["lynched"]].display_name
                await interaction.response.send_message(f"⚖️ **{name}** foi linchado pela vila!")
            for extra in result["extra_deaths"]:
                await channel.send(f"💔 {game.players[extra].display_name} morreu de amor pelo Casal Apaixonado.")
            if result["hunter_pending"]:
                name = game.players[result["hunter_pending"]].display_name
                await channel.send(f"🏹 {name} era o Caçador! Ele pode usar `/vingar` na DM.")
                await self.dm(result["hunter_pending"], "🏹 Você morreu! Use `/vingar @jogador` para atirar em alguém antes de partir.")

            if await self.maybe_end_game(game, channel):
                return
            await self.announce_night_start(game)

        else:
            await interaction.response.send_message("Não há fase para avançar agora.", ephemeral=True)

    # ---------- votação do dia ----------

    @app_commands.command(name="votar", description="Vota para linchar um jogador durante o dia")
    @app_commands.describe(jogador="Jogador em quem votar")
    async def votar(self, interaction: discord.Interaction, jogador: discord.Member):
        game = self.find_game_by_channel(interaction.channel_id)
        if not game or game.phase != Phase.DAY_VOTE:
            await interaction.response.send_message("Não há votação aberta agora.", ephemeral=True)
            return
        voter = game.get_player(interaction.user.id)
        target = game.get_player(jogador.id)
        if not voter or not voter.alive:
            await interaction.response.send_message("Só jogadores vivos podem votar.", ephemeral=True)
            return
        if not target or not target.alive:
            await interaction.response.send_message("Alvo inválido.", ephemeral=True)
            return
        game.record_day_vote(voter.user_id, target.user_id)
        await interaction.response.send_message(f"🗳️ {interaction.user.mention} votou em {jogador.display_name}.")

    # ---------- ações noturnas (DM) ----------

    def _dm_only(self, interaction: discord.Interaction) -> bool:
        return interaction.guild is None

    @app_commands.command(name="matar", description="[Lobisomem] Escolhe a vítima da noite (use na DM)")
    @app_commands.describe(jogador="Jogador a ser devorado")
    async def matar(self, interaction: discord.Interaction, jogador: discord.User):
        game = self.find_game_by_player(interaction.user.id)
        if not game or game.phase != Phase.NIGHT or game.night_step != 1:
            await interaction.response.send_message("Não é hora de agir.", ephemeral=True)
            return
        actor = game.get_player(interaction.user.id)
        target = game.get_player(jogador.id)
        if not actor or actor.role != Role.LOBISOMEM or not actor.alive:
            await interaction.response.send_message("Você não é um lobisomem vivo.", ephemeral=True)
            return
        if not target or not target.alive or target.role == Role.LOBISOMEM:
            await interaction.response.send_message("Alvo inválido.", ephemeral=True)
            return
        game.record_wolf_vote(actor.user_id, target.user_id)
        await interaction.response.send_message(f"🐺 Você votou para devorar {target.display_name}.")

    @app_commands.command(name="investigar", description="[Vidente] Investiga o papel de um jogador (use na DM)")
    @app_commands.describe(jogador="Jogador a investigar")
    async def investigar(self, interaction: discord.Interaction, jogador: discord.User):
        game = self.find_game_by_player(interaction.user.id)
        if not game or game.phase != Phase.NIGHT:
            await interaction.response.send_message("Não é hora de agir.", ephemeral=True)
            return
        actor = game.get_player(interaction.user.id)
        target = game.get_player(jogador.id)
        if not actor or actor.role != Role.VIDENTE or not actor.alive:
            await interaction.response.send_message("Você não é a vidente.", ephemeral=True)
            return
        if not target or not target.alive:
            await interaction.response.send_message("Alvo inválido.", ephemeral=True)
            return
        game.record_seer_target(target.user_id)
        await interaction.response.send_message(f"🔮 {target.display_name} é: **{target.role.value}**")

    @app_commands.command(name="salvar", description="[Bruxa] Cura a vítima dos lobos nesta noite (use na DM)")
    async def salvar(self, interaction: discord.Interaction):
        game = self.find_game_by_player(interaction.user.id)
        if not game or game.phase != Phase.NIGHT or game.night_step != 2:
            await interaction.response.send_message("Não é hora de agir.", ephemeral=True)
            return
        actor = game.get_player(interaction.user.id)
        if not actor or actor.role != Role.BRUXA or not actor.alive:
            await interaction.response.send_message("Você não é a bruxa.", ephemeral=True)
            return
        if game.witch_heal_used:
            await interaction.response.send_message("Você já usou sua poção de cura.", ephemeral=True)
            return
        game.record_witch_heal()
        await interaction.response.send_message("🧪 Você usou a poção de cura. A vítima dos lobos será salva.")

    @app_commands.command(name="envenenar", description="[Bruxa] Mata um jogador com veneno (use na DM)")
    @app_commands.describe(jogador="Jogador a envenenar")
    async def envenenar(self, interaction: discord.Interaction, jogador: discord.User):
        game = self.find_game_by_player(interaction.user.id)
        if not game or game.phase != Phase.NIGHT or game.night_step != 2:
            await interaction.response.send_message("Não é hora de agir.", ephemeral=True)
            return
        actor = game.get_player(interaction.user.id)
        target = game.get_player(jogador.id)
        if not actor or actor.role != Role.BRUXA or not actor.alive:
            await interaction.response.send_message("Você não é a bruxa.", ephemeral=True)
            return
        if game.witch_poison_used:
            await interaction.response.send_message("Você já usou sua poção de veneno.", ephemeral=True)
            return
        if not target or not target.alive:
            await interaction.response.send_message("Alvo inválido.", ephemeral=True)
            return
        game.record_witch_poison(target.user_id)
        await interaction.response.send_message(f"🧪 Você envenenou {target.display_name}.")

    @app_commands.command(name="flechar", description="[Cupido] Escolhe o Casal Apaixonado na 1ª noite (use na DM)")
    @app_commands.describe(jogador1="Primeiro jogador", jogador2="Segundo jogador")
    async def flechar(self, interaction: discord.Interaction, jogador1: discord.User, jogador2: discord.User):
        game = self.find_game_by_player(interaction.user.id)
        if not game or game.phase != Phase.NIGHT or not game.is_first_night():
            await interaction.response.send_message("Só é possível flechar na primeira noite.", ephemeral=True)
            return
        actor = game.get_player(interaction.user.id)
        p1 = game.get_player(jogador1.id)
        p2 = game.get_player(jogador2.id)
        if not actor or actor.role != Role.CUPIDO or not actor.alive:
            await interaction.response.send_message("Você não é o cupido.", ephemeral=True)
            return
        if game.cupid_done:
            await interaction.response.send_message("Você já escolheu o casal.", ephemeral=True)
            return
        if not p1 or not p2 or jogador1.id == jogador2.id:
            await interaction.response.send_message("Escolha dois jogadores válidos e diferentes.", ephemeral=True)
            return
        game.record_cupid(p1.user_id, p2.user_id)
        await interaction.response.send_message(f"💘 {p1.display_name} e {p2.display_name} agora são o Casal Apaixonado!")
        await self.dm(p1.user_id, f"💘 Você está apaixonado por {p2.display_name}! Se um de vocês morrer, o outro morre junto.")
        await self.dm(p2.user_id, f"💘 Você está apaixonado por {p1.display_name}! Se um de vocês morrer, o outro morre junto.")

    @app_commands.command(name="vingar", description="[Caçador] Atira em alguém ao morrer (use na DM)")
    @app_commands.describe(jogador="Jogador para atirar")
    async def vingar(self, interaction: discord.Interaction, jogador: discord.User):
        game = self.find_game_by_player(interaction.user.id)
        if not game or game.pending_hunter_revenge != interaction.user.id:
            await interaction.response.send_message("Você não tem uma vingança pendente.", ephemeral=True)
            return
        target = game.get_player(jogador.id)
        if not target or not target.alive:
            await interaction.response.send_message("Alvo inválido.", ephemeral=True)
            return
        game.apply_hunter_revenge(target.user_id)
        await interaction.response.send_message(f"🏹 Você atirou em {target.display_name}!")
        channel = self.bot.get_channel(game.channel_id)
        if channel:
            await channel.send(f"🏹 Ao morrer, o Caçador atirou em **{target.display_name}**, que também morreu!")
        await self.maybe_end_game(game, channel)


async def setup(bot: commands.Bot):
    await bot.add_cog(CidadeDormeCog(bot))

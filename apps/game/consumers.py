from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.game import Role
from .models import GameSession, Participant


class GameConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        self.user = self.scope.get('user')

        self.session, self.participant = await self.get_session_and_participant()
        if not self.session or not self.participant or not self.participant.is_alive:
            await self.close(code=4001)
            return

        self.host_id = self.session.room.host_id
        self.phase = self.session.phase
        self.group = f'game_{self.session_id}'
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

        await self.send_json({
            'type': 'your_role',
            'role': self.participant.role,
        })

    async def disconnect(self, close_code):
        if hasattr(self, 'group'):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive_json(self, content):
        event = content.get('type')
        handler = {
            'mafia_kill': self.handle_mafia_kill,
            'detective_investigate': self.handle_detective_investigate,
            'doctor_protect': self.handle_doctor_protect,
            'vote': self.handle_vote,
            'next_phase': self.handle_next_phase,
        }.get(event)

        if handler:
            await handler(content)

    async def handle_mafia_kill(self, content):
        if self.phase != GameSession.Phase.NIGHT.value:
            return
        if self.participant.role != Role.MAFIA:
            return
        target_id = content['target_id']
        await self.atomic_add_mafia_vote(str(self.user.id), target_id)

    async def handle_detective_investigate(self, content):
        if self.phase != GameSession.Phase.NIGHT.value:
            return
        if self.participant.role != Role.DETECTIVE:
            return
        target_id = content['target_id']
        is_mafia = await self.check_role(target_id, Role.MAFIA)
        await self.send_json({
            'type': 'investigation_result',
            'target_id': target_id,
            'is_mafia': is_mafia,
        })

    async def handle_doctor_protect(self, content):
        if self.phase != GameSession.Phase.NIGHT.value:
            return
        if self.participant.role != Role.DOCTOR:
            return
        target_id = content['target_id']
        await self.atomic_set_doctor_protect(target_id)

    async def handle_vote(self, content):
        if self.phase != GameSession.Phase.VOTING.value:
            return
        target_id = content['target_id']
        await self.channel_layer.group_send(self.group, {
            'type': 'vote_cast',
            'user_id': self.user.id,
            'username': self.user.username,
            'target_id': target_id,
        })

    async def handle_next_phase(self, content):
        if self.host_id != self.user.id:
            return
        new_phase = await self.advance_phase()
        await self.channel_layer.group_send(self.group, {
            'type': 'phase_changed',
            'phase': new_phase,
            'round_number': await self.get_round_number(),
        })

        if new_phase == GameSession.Phase.DAY.value:
            await self.resolve_night()

        if new_phase == GameSession.Phase.ENDED.value:
            await self.channel_layer.group_send(self.group, {
                'type': 'game_over',
                'winner': await self.get_winner(),
            })

    async def resolve_night(self):
        night = self.session.night_actions or {}
        mafia_votes = night.get('mafia_votes', {})
        if not mafia_votes:
            return

        tally = {}
        for target_id in mafia_votes.values():
            tally[target_id] = tally.get(target_id, 0) + 1
        victim_id = max(tally, key=tally.get)

        protected = night.get('doctor_protect')
        if protected == victim_id:
            victim_id = None

        if victim_id:
            await self.kill_player(int(victim_id))
            winner = await self.check_win_condition()
            if winner:
                await self.channel_layer.group_send(self.group, {
                    'type': 'game_over',
                    'winner': winner,
                })
            else:
                await self.channel_layer.group_send(self.group, {
                    'type': 'player_killed',
                    'user_id': int(victim_id),
                })

        await self.clear_night_actions()

    async def vote_cast(self, event):
        await self.send_json({
            'type': 'vote_cast',
            'user_id': event['user_id'],
            'username': event['username'],
            'target_id': event['target_id'],
        })

    async def phase_changed(self, event):
        self.phase = event['phase']
        await self.send_json({
            'type': 'phase_changed',
            'phase': event['phase'],
            'round_number': event['round_number'],
        })

    async def player_killed(self, event):
        await self.send_json({
            'type': 'player_killed',
            'user_id': event['user_id'],
        })

    async def game_over(self, event):
        await self.send_json({
            'type': 'game_over',
            'winner': event['winner'],
        })

    @database_sync_to_async
    def get_session_and_participant(self):
        try:
            session = GameSession.objects.select_related('room__host').get(pk=self.session_id)
            participant = session.participant_set.select_related('user').get(user=self.user)
            return session, participant
        except (GameSession.DoesNotExist, Participant.DoesNotExist):
            return None, None

    @database_sync_to_async
    def check_role(self, user_id, role):
        return Participant.objects.filter(
            game_session_id=self.session_id, user_id=user_id, role=role
        ).exists()

    @database_sync_to_async
    def atomic_add_mafia_vote(self, voter_key, target_id):
        session = GameSession.objects.get(pk=self.session_id)
        night = session.night_actions or {}
        night.setdefault('mafia_votes', {})[voter_key] = target_id
        GameSession.objects.filter(pk=self.session_id).update(night_actions=night)
        self.session.night_actions = night

    @database_sync_to_async
    def atomic_set_doctor_protect(self, target_id):
        session = GameSession.objects.get(pk=self.session_id)
        night = session.night_actions or {}
        night['doctor_protect'] = target_id
        GameSession.objects.filter(pk=self.session_id).update(night_actions=night)
        self.session.night_actions = night

    @database_sync_to_async
    def clear_night_actions(self):
        GameSession.objects.filter(pk=self.session_id).update(night_actions={})
        self.session.night_actions = {}

    @database_sync_to_async
    def kill_player(self, user_id):
        Participant.objects.filter(game_session_id=self.session_id, user_id=user_id).update(is_alive=False)

    @database_sync_to_async
    def advance_phase(self):
        order = [
            GameSession.Phase.NIGHT,
            GameSession.Phase.DAY,
            GameSession.Phase.VOTING,
        ]
        session = GameSession.objects.get(pk=self.session_id)
        phases_by_value = {p.value: p for p in order}
        current = phases_by_value[session.phase]
        idx = order.index(current)
        if idx == len(order) - 1:
            session.round_number += 1
            session.phase = order[0].value
        else:
            session.phase = order[idx + 1].value
        session.save()
        self.session = session
        return session.phase

    @database_sync_to_async
    def get_round_number(self):
        return GameSession.objects.get(pk=self.session_id).round_number

    @database_sync_to_async
    def get_winner(self):
        return GameSession.objects.get(pk=self.session_id).winner

    @database_sync_to_async
    def check_win_condition(self):
        session = GameSession.objects.get(pk=self.session_id)
        alive = session.participant_set.filter(is_alive=True)
        mafia_alive = alive.filter(role=Role.MAFIA).count()
        villager_alive = alive.exclude(role=Role.MAFIA).count()

        if mafia_alive == 0:
            session.winner = GameSession.Outcome.VILLAGERS
            session.phase = GameSession.Phase.ENDED
            session.save()
            self._record_results(session)
            return session.winner
        elif mafia_alive >= villager_alive:
            session.winner = GameSession.Outcome.MAFIA
            session.phase = GameSession.Phase.ENDED
            session.save()
            self._record_results(session)
            return session.winner
        return None

    @staticmethod
    def _record_results(session):
        for p in session.participant_set.all():
            p.won = (p.role == Role.MAFIA) == (session.winner == GameSession.Outcome.MAFIA)
            p.save()

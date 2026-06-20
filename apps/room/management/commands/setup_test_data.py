from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.game import Role
from apps.game.models import GameSession, Participant
from apps.room.models import Room

User = get_user_model()

TEST_USERS = [
    ("alice", "testpass123", "alice@test.com"),
    ("bob", "testpass123", "bob@test.com"),
    ("charlie", "testpass123", "charlie@test.com"),
    ("diana", "testpass123", "diana@test.com"),
    ("eve", "testpass123", "eve@test.com"),
    ("frank", "testpass123", "frank@test.com"),
]


class Command(BaseCommand):
    help = "Create test users, room, and game session"

    def handle(self, *args, **options):
        users = []
        for username, password, email in TEST_USERS:
            user, created = User.objects.get_or_create(username=username, defaults={"email": email})
            if created:
                user.set_password(password)
                user.save()
                self.stdout.write(f"Created user: {username}")
            else:
                self.stdout.write(f"User exists: {username}")
            users.append(user)

        # Delete old test room + session
        Room.objects.filter(code="TEST1234").delete()

        room = Room.objects.create(
            host=users[0],
            name="Test Room",
            code="TEST1234",
            max_members=6,
            status=Room.Status.WAITING,
        )
        for u in users[:4]:
            room.members.add(u)
        self.stdout.write(f"Created room: {room.name} ({room.code})")

        session = GameSession.objects.create(room=room)
        roles = [Role.MAFIA, Role.DETECTIVE, Role.DOCTOR, Role.VILLAGER]
        for user, role in zip(users[:4], roles):
            Participant.objects.create(user=user, game_session=session, role=role)

        self.stdout.write(f"Created game session: id={session.pk}")
        self.stdout.write(f"Room code: {room.code}")
        self.stdout.write(f"Session id: {session.pk}")
        self.stdout.write("\nPasswords: testpass123")
        self.stdout.write("Tokens available at POST /api/accounts/token/")

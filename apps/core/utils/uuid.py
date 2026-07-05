import uuid


def generate_code(length:int =8):
    return uuid.uuid4().hex[:length].upper()

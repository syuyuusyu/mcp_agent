import random

def random_string(length=10):
    # 自定义字符集
    uppercase = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    lowercase = 'abcdefghijklmnopqrstuvwxyz'
    digits = '0123456789'
    characters = uppercase + lowercase + digits
    
    return ''.join(random.choice(characters) for _ in range(length))
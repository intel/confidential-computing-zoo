import random, time

kv_dict = {}

key_choice = '1234567890'
value_choice = '1234567890abcdefghijklmnopqrstuvwxyz!@#$%^&*()'

def gen_rand_chr(choice):
    return random.choice(choice)

def gen_rand_str(choice, length):
    return ''.join([gen_rand_chr(choice) for _ in range(length)])

def generate_kv_pair():
    kv = {
        "uuid" + gen_rand_str(key_choice, 8) : gen_rand_str(value_choice, 16)
    }
    kv_dict.update(kv)

for _ in range(5):
    generate_kv_pair()

print(kv_dict)

while True:
    time.sleep(5)

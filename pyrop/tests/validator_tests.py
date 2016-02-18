import unittest, logging
import pyvex, archinfo

from gadget import *
from validator import *

class ValidatorTests(unittest.TestCase):

  def run_test(self, arch, tests):
    code_gadget_list = self.make_tests(arch, tests)
    validator = Validator(arch)

    for code, gadget, is_valid in code_gadget_list:
      print "Validating gadget", gadget
      irsb = pyvex.IRSB(code, 0x40000, arch)
      result = validator.validate_gadget(gadget, irsb)
      if result != is_valid:
        irsb.pp()
        
      self.assertEqual(result, is_valid)

  def make_tests(self, arch, tests):
    code_gadget_list = []
    for (code, gadget_type, inputs, outputs, params, clobber, stack, ip, is_valid) in tests:
      input_regs = []
      for input_reg_name in inputs:
        input_regs.append(arch.registers[input_reg_name][0])
      clobber_regs = []
      for clobber_reg_name in clobber:
        clobber_regs.append(arch.registers[clobber_reg_name][0])
      output_regs = []
      for output_reg_name in outputs:
        output_regs.append(arch.registers[output_reg_name][0])

      gadget = gadget_type(arch, 0x40000, input_regs, output_regs, params, clobber, stack, ip)
      code_gadget_list.append((code, gadget, is_valid))
    return code_gadget_list

  def test_amd64(self):
    arch = archinfo.ArchAMD64()
    tests = [
      ('\xff\xe0',                                         Jump, ['rax'], ['rip'], [], [], 0, None, True), # jmp rax
      ('\x48\x93\xc3',                                     MoveReg, ['rbx'], ['rax'], [], ['rbx'], 8, 0, True), # xchg rbx, rax; ret
      ('\x48\x93\xc3',                                     MoveReg, ['rax'], ['rbx'], [], ['rax'], 8, 0, True), # xchg rbx, rax; ret
      ('\x48\x89\xcb\xc3',                                 MoveReg, ['rcx'], ['rbx'], [], [], 8, 0, True), # mov rbx, rcx; ret
      ('\x48\xbb\xff\xee\xdd\xcc\xbb\xaa\x99\x88\xc3',     LoadConst, [], ['rbx'], [0x8899aabbccddeeff], [], 8, 0, True), # movabs rbx,0x8899aabbccddeeff; ret
      ('\x48\x01\xc3\xc3',                                 AddGadget, ['rbx','rax'], ['rbx'], [], [], 8, 0, True), # add rbx, rax; ret
      ('\x5f\xc3',                                         LoadMem, ['rsp'], ['rdi'], [0], [], 0x10, 8, True), # pop rdi; ret
      ('\x48\x8b\x43\x08\xc3',                             LoadMem, ['rbx'], ['rax'], [8], [], 8, 0, True), # mov rax,QWORD PTR [rbx+0x8]; ret
      ('\x48\x8b\x07\xc3',                                 LoadMem, ['rdi'], ['rax'], [0], [], 8, 0, True), # mov rax,QWORD PTR [rbx+0x8]; ret
      ('\x48\x89\x03\xc3',                                 StoreMem, ['rbx','rax'], [], [0], [], 8, 0, True), # mov QWORD PTR [rbx],rax; ret
      ('\x48\x89\x43\x08\xc3',                             StoreMem, ['rbx','rax'], [], [8], [], 8, 0, True), # mov QWORD PTR [rbx+0x8],rax; ret
      ('\x48\x89\x44\x24\x08\xc3',                         StoreMem, ['rsp','rax'], [], [8], [], 8, 0, True), # mov QWORD PTR [rsp+0x8],rax; ret
      ('\x48\x03\x03\xc3',                                 LoadAddGadget, ['rbx','rax'], ['rax'], [0], [], 8, 0, True), # add rax,QWORD PTR [rsp+0x8]; ret
      ('\x48\x01\x43\xf8\xc3',                             StoreAddGadget, ['rbx','rax'], ['rax'], [-8], [], 8, 0, True), # add QWORD PTR [rbx-0x8],rax; ret
      ('\x59\x48\x89\xcb\x48\xc7\xc1\x05\x00\x00\x00\xc3', LoadMem, ['rsp'], ['rbx'], [0], ['rcx'], 0x10, 8, True), # pop rcx; mov rbx,rcx; mov rcx,0x5; ret
      ('\x59\x48\x89\xcb\x48\xc7\xc1\x05\x00\x00\x00\xc3', LoadConst, [], ['rcx'], [5], ['rbx'], 0x10, 8, True), # pop rcx; mov rbx,rcx; mov rcx,0x5; ret
    ]
    self.run_test(arch, tests)

  def test_arm(self):
    arch = archinfo.ArchARM()
    tests = [
      ('\x08\x80\xbd\xe8', LoadMem, ['sp'], ['r3'], [0], [], 0x8, 4, True), # pop {r3, pc}
      ('\x02\x00\xa0\xe1\x04\xf0\x9d\xe4', MoveReg, ['r2'], ['r0'], [0], [], 4, 0, True), # mov r0, r2; pop {pc}
      ('\xf0\x87\xbd\xe8', LoadMem, ['sp'], ['r4'],  [0x00], ['r5', 'r6', 'r7', 'r8', 'r9', 'r10'], 0x20, 0x1c, True), # pop {r4, r5, r6, r7, r8, r9, sl, pc}
      ('\xf0\x87\xbd\xe8', LoadMem, ['sp'], ['r5'],  [0x04], ['r4', 'r6', 'r7', 'r8', 'r9', 'r10'], 0x20, 0x1c, True), # pop {r4, r5, r6, r7, r8, r9, sl, pc}
      ('\xf0\x87\xbd\xe8', LoadMem, ['sp'], ['r6'],  [0x08], ['r5', 'r4', 'r7', 'r8', 'r9', 'r10'], 0x20, 0x1c, True), # pop {r4, r5, r6, r7, r8, r9, sl, pc}
      ('\xf0\x87\xbd\xe8', LoadMem, ['sp'], ['r7'],  [0x0c], ['r5', 'r6', 'r4', 'r8', 'r9', 'r10'], 0x20, 0x1c, True), # pop {r4, r5, r6, r7, r8, r9, sl, pc}
      ('\xf0\x87\xbd\xe8', LoadMem, ['sp'], ['r8'],  [0x10], ['r5', 'r6', 'r7', 'r4', 'r9', 'r10'], 0x20, 0x1c, True), # pop {r4, r5, r6, r7, r8, r9, sl, pc}
      ('\xf0\x87\xbd\xe8', LoadMem, ['sp'], ['r9'],  [0x14], ['r5', 'r6', 'r7', 'r8', 'r4', 'r10'], 0x20, 0x1c, True), # pop {r4, r5, r6, r7, r8, r9, sl, pc}
      ('\xf0\x87\xbd\xe8', LoadMem, ['sp'], ['r10'], [0x18], ['r5', 'r6', 'r7', 'r8', 'r9', 'r4'],  0x20, 0x1c, True), # pop {r4, r5, r6, r7, r8, r9, sl, pc}
      ('\x04\xe0\x9d\xe5\x08\xd0\x8d\xe2\x0c\x00\xbd\xe8\x1e\xff\x2f\xe1', # ldr lr, [sp, #4]; add sp, sp, #8; pop {r2, r3}; bx lr
        LoadMem, ['sp'], ['r2'], [0x8], ['lr','r3'], 0x8, 4, True), 
      ('\x04\xe0\x9d\xe5\x08\xd0\x8d\xe2\x0c\x00\xbd\xe8\x1e\xff\x2f\xe1', # ldr lr, [sp, #4]; add sp, sp, #8; pop {r2, r3}; bx lr
        LoadMem, ['sp'], ['r3'], [0xc], ['lr','r2'], 0x8, 4, True), 
      ('\x1f\x40\xbd\xe8\x1c\xff\x2f\xe1', LoadMemJump, ['sp', 'r12'], ['r0'], [0], ['lr', 'r1', 'r2', 'r3', 'r4'], 0x18, None, True), # pop {r0, r1, r2, r3, r4, lr}; bx r12
      ('\x1f\x40\xbd\xe8\x1c\xff\x2f\xe1', LoadMemJump, ['sp', 'r12'], ['r1'], [0], ['lr', 'r0', 'r2', 'r3', 'r4'], 0x18, None, True), # pop {r0, r1, r2, r3, r4, lr}; bx r12
      ('\x1f\x40\xbd\xe8\x1c\xff\x2f\xe1', LoadMemJump, ['sp', 'r12'], ['r2'], [0], ['lr', 'r1', 'r0', 'r3', 'r4'], 0x18, None, True), # pop {r0, r1, r2, r3, r4, lr}; bx r12
      ('\x1f\x40\xbd\xe8\x1c\xff\x2f\xe1', LoadMemJump, ['sp', 'r12'], ['r3'], [0], ['lr', 'r1', 'r2', 'r0', 'r4'], 0x18, None, True), # pop {r0, r1, r2, r3, r4, lr}; bx r12
      ('\x1f\x40\xbd\xe8\x1c\xff\x2f\xe1', LoadMemJump, ['sp', 'r12'], ['r4'], [0], ['lr', 'r1', 'r2', 'r3', 'r0'], 0x18, None, True), # pop {r0, r1, r2, r3, r4, lr}; bx r12
      ('\x1f\x40\xbd\xe8\x1c\xff\x2f\xe1', LoadMemJump, ['sp', 'r12'], ['lr'], [0], ['r0', 'r1', 'r2', 'r3', 'r4'], 0x18, None, True), # pop {r0, r1, r2, r3, r4, lr}; bx r12
      ('\x1f\x40\xbd\xe8\x1c\xff\x2f\xe1', Jump, ['r12'], ['pc'], [0], ['lr','r0', 'r1', 'r2', 'r3', 'r4'], 0x18, None, True), # pop {r0, r1, r2, r3, r4, lr}; bx r12
      ('\x04\xe0\x9d\xe4\x13\xff\x2f\xe1', LoadMemJump, ['sp', 'r3'], ['lr'], [0], [], 0x4, None, True), # pop {lr}; bx r3
      ('\x04\xe0\x9d\xe4\x13\xff\x2f\xe1', Jump, ['r3'], ['pc'], [0], [], 0x4, None, True), # pop {lr}; bx r3
    ]
    self.run_test(arch, tests)

  def skip_test_mips(self):
    arch = archinfo.ArchMIPS32('Iend_BE')
    tests = [
      ('\x8f\xbf\x00\x10\x8f\xb0\x00\x08\x03\xe0\x00\x08\x20\x00\xBD\x27',  # # lw ra,16(sp); lw s0,8(sp); jr ra; addiu $sp, 0x20
        LoadMem, ['sp'], ['s0'], [8], ['ra'], 0x20, 0x10, True),
    ]
    self.run_test(arch, tests)

  def test_ppc(self):
    arch = archinfo.ArchPPC32()
    tests = [
      ('\x08\x00\xe1\x83\x04\x00\x01\x80\xa6\x03\x08\x7c\x10\x00\x21\x38\x20\x00\x80\x4e', # lwz r31,8(r1); lwz r0,4(r1); mtlr r0; addi r1,r1,16; blr
        LoadMem, ['r1'], ['r31'], [8], ['r0', 'lr'], 0x10, 0x4, True),
    ]
    self.run_test(arch, tests)

if __name__ == '__main__':
  unittest.main()

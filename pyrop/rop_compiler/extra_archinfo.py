# This file contains some architecture specific information that pyvex doesn't include
import collections

"""Registers reported by pyvex that we don't care to look for, per architecture"""
IGNORED_REGISTERS = collections.defaultdict(list, {
  "X86"   : ['bp', 'cc_dep1', 'cc_dep2', 'cc_ndep', 'cc_op', 'cs', 'd', 'ds', 'es', 'fc3210', 'fpround', 'fpu_regs',
             'fpu_t0', 'fpu_t1', 'fpu_t2', 'fpu_t3', 'fpu_t4', 'fpu_t5', 'fpu_t6', 'fpu_t7', 'fpu_tags', 'fs', 'ftop', 'gdt',
             'gs', 'id', 'ldt', 'mm0', 'mm1', 'mm2', 'mm3', 'mm4', 'mm5', 'mm6', 'mm7', 'ss', 'sseround', 'st0', 'st1',
             'st2', 'st3', 'st4', 'st5', 'st6', 'st7', 'xmm0', 'xmm1', 'xmm2', 'xmm3', 'xmm4', 'xmm5', 'xmm6', 'xmm7'],
  "AMD64" : [ "cc_dep1", "cc_dep2", "cc_ndep", "cc_op", "d", "fpround", "fs", "sseround"  ]
})

func_calling_convention = collections.defaultdict(list, {
  "AMD64" : ["rdi", "rsi", "rdx", "rcx", "r8", "r9"],
  "ARMEL" : ["r0", "r1", "r2", "r3"]
})

MPROTECT_SYSCALL = { "AMD64" : 10 }

syscall_calling_convention = [ "rdi", "rsi", "rdx", "r10", "r8", "r9" ]

ALIGNED_ARCHS = ['PPC32']

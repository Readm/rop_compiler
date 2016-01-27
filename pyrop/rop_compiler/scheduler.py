# This file contains the logic to combine a set of gadgets and implement the desired goals
import struct, logging, collections
import goal as go, gadget as ga
import archinfo

PAGE_MASK = 0xfffffffffffff000
PROT_RWX = 7
MPROTECT_SYSCALL = 10

class Scheduler(object):
  """This class takes a set of gadgets and combines them together to implement the given goals"""

  func_calling_convention = collections.defaultdict(list, {
    "AMD64" : ["rdi", "rsi", "rdx", "rcx", "r8", "r9"],
    "ARMEL" : ["r0", "r1", "r2", "r3"]
  })

  #syscall_calling_convention = [ "rdi", "rsi", "rdx", "r10", "r8", "r9" ]  # TODO cover the syscall case

  IGNORED_REGISTERS = collections.defaultdict(list, {
    "AMD64" : [ "cc_dep1", "cc_dep2", "cc_ndep", "cc_op", "d", "fpround", "fs", "sseround"  ]
  })

  def __init__(self, gadgets, goal_resolver, arch = archinfo.ArchAMD64, level = logging.WARNING):
    logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    self.logger = logging.getLogger(self.__class__.__name__)
    self.logger.setLevel(level)

    self.arch = arch()
    self.gadgets = gadgets
    self.write_memory_chains = []
    self.store_mem_gadgets = collections.defaultdict(dict)

    self.goal_resolver = goal_resolver
    self.goals = goal_resolver.get_goals()
    self.chain = self.chain_gadgets()

  def get_all_registers(self):
    registers = dict(self.arch.registers)
    for reg in self.IGNORED_REGISTERS[self.arch.name]:
      registers.pop(reg)
    reg_numbers = []
    for name, (number, size) in registers.items():
      reg_numbers.append(number)
    return reg_numbers

  def reg_name(self, reg_number):
    return self.arch.translate_register_name(reg_number)

  def reg_number(self, reg_name):
    return self.arch.registers[reg_name][0]

  def get_chain(self):
    """Returns the compiled ROP chain"""
    return self.chain

  def find_load_stack_gadget(self, register, no_clobber = None):
    """This method finds the best gadget (lowest complexity) to load a register from the stack"""
    best = best_complexity = None
    for gadget in self.gadgets:
      if (type(gadget) == ga.LoadMem and gadget.inputs[0] == self.arch.registers['sp'][0] # It's a load from the stack (most likely a pop)
        and register == gadget.output # and it's for the correct register
        and (no_clobber == None or not gadget.clobbers_registers(no_clobber))
        and (best == None or best_complexity < gadget.complexity())): # and it's got a better complexity than the current one
          best = gadget
          best_complexity = best.complexity()

    if best != None:
      self.logger.debug("Found LoadStack %s Gadget: %s", self.reg_name(register), best)

    # TODO Synthesize gadgets for missing types
    return best

  def find_gadget(self, gadget_type, input_registers = None, output_register = None, no_clobber = None):
    """This method will find the best gadget (lowest complexity) given the search criteria"""
    best = best_complexity = None
    for gadget in self.gadgets:
      if (type(gadget) == gadget_type # Match the requested type
        and (input_registers == None # Not looking for a gadget with a specific register as input
          or (gadget.inputs[0] == input_registers[0] # Only looking for one specific input
            and (len(gadget.inputs) == 1 or gadget.inputs[1] == input_registers[1]))) # Also looking to match the second input
        and (output_register == None or gadget.output == output_register) # looking to match the output
        and (no_clobber == None or not gadget.clobbers_registers(no_clobber)) # Can't clobber anything we need
        and (best == None or best_complexity > gadget.complexity())): # and it's got a better complexity than the current one
          best = gadget
          best_complexity = best.complexity()

    if best != None:
      self.logger.debug("Found %s %s Gadget: %s", gadget_type.__name__, self.reg_name(best.inputs[0]), best)

    # TODO Synthesize gadgets for missing types
    return best

  def find_store_mem_gadgets(self, addr_reg, value_reg):
    """This method finds a gadget that writes the value in one register to the address in another"""
    if value_reg in self.store_mem_gadgets[addr_reg]:
      return self.store_mem_gadgets[addr_reg][value_reg]

    best = None
    for gadget in self.gadgets:
      if type(gadget) != ga.StoreMem:
        continue

      if (type(gadget) == ga.StoreMem
        and addr_reg == gadget.inputs[0]
        and value_reg == gadget.inputs[1]
        and (best == None or best.complexity() > gadget.complexity())): # and it's got a better complexity than the current one
          best = gadget

    self.store_mem_gadgets[addr_reg][value_reg] = best
    if best != None:
      self.logger.debug("Found StoreMem(%s, %s) Gadget:%s", self.reg_name(addr_reg), self.reg_name(value_reg), best)
    return best

  def combined_complexity(self, chain):
    """This method determines the complexity of a gadget chain by summing the complexity of the individual gadgets in it"""
    return sum([gadget.complexity() for gadget in chain])

  def chain_uses_registers(self, chain, registers):
    """This method determines if any gadgets in the specified chain use any of the specified registers"""
    for gadget in chain:
      for reg in registers:
        if gadget.uses_register(avoid_reg):
          return True
    return False

  def find_write_memory_gadgets(self):
    """This method determines a set of gadget sequences that will write a value to memory"""

    self.write_memory_chains = []
    for addr_reg in self.get_all_registers():
      # First find a gadget to set the address register
      load_addr_gadget = self.find_load_stack_gadget(addr_reg)
      if load_addr_gadget == None:
        continue

      for value_reg in self.get_all_registers():
        if addr_reg == value_reg:
          continue

        # Then find a gadget to set the value register
        load_value_gadget = self.find_load_stack_gadget(value_reg, [addr_reg])
        if load_value_gadget == None:
          continue

        # Finally find a gadget to set the memory at the address register to the value in the value register
        store_mem_gadget = self.find_store_mem_gadgets(addr_reg, value_reg)
        if store_mem_gadget != None:
          chain = [load_addr_gadget, load_value_gadget, store_mem_gadget]
          complexity = self.combined_complexity(chain)
          self.write_memory_chains.append((chain, complexity))

  def get_write_memory_gadget(self, avoid_registers = None):
    """This method iterates over write_memory_chains and finds the best gadget chain to write memory with, while excluding any
      specified registers"""

    best = best_complexity = None
    for (chain, complexity) in self.write_memory_chains:
      if best_complexity == None or best_complexity > complexity:
        if avoid_registers == None or not self.chain_uses_registers(chain, avoid_registers):
          best_complexity = complexity
          best = chain

    if best == None:
      raise RuntimeError("Could not find a way to write to memory")
    return best

  def ap(self, address):
    """Packs an address into a string. ap is short for Address Pack"""
    formats = { 32 : "I", 64 : "Q" }
    if address < 0:
      address = (2**self.arch.bits) + address
    return struct.pack(formats[self.arch.bits], address)

  def create_function_chain(self, goal, end_address = 0x4444444444444444):
    """This method returns a ROP chain that will call a function"""
    self.logger.info("Creating function chain for %s(%s) and finishing with a return to 0x%x", goal.name,
      ",".join([hex(x) for x in goal.arguments]), end_address)

    # TODO add the ability to do strings arguments by writing the string to memory first, and then using the string's address

    # Look for gadgets to set each of the arguments
    arg_gadgets = []
    no_clobber = []
    for i in range(len(goal.arguments)):
      reg = self.reg_number(self.func_calling_convention[self.arch.name][i])
      arg_gadget = self.find_load_stack_gadget(reg, no_clobber)
      if arg_gadget == None:
        # TODO Rearrange the order of setting gadgets so we can still use gadgets that clobber another register
        msg = "No gadget found to set {} register during function call to {}".format(self.reg_name(reg), goal.name)
        self.logger.critical(msg)
        raise RuntimeError(msg)
      arg_gadgets.append(arg_gadget)
      no_clobber.append(reg)

    # Set the arguments for the function
    chain = ""
    for i in range(len(arg_gadgets)):
      next_address = goal.address
      if i + 1 < len(goal.arguments):
        next_address = arg_gadgets[i + 1].address
      chain += arg_gadgets[i].chain(next_address, goal.arguments[i])

    chain = chain + self.ap(end_address)
    return (chain, arg_gadgets[0].address)

  def create_read_add_jmp_function_chain(self, address, offset, arguments, end_address):
    """This method creates a ROP chain that will read from a specified address, apply an offset, and then call that address with
      a set of provided arguments"""

    jump_gadget = None
    arg_gadgets = []

    # First, look for all the needed gadgets
    original_offset = offset
    for jump_reg in self.get_all_registers():
      read_gadget = set_read_addr_gadget = None
      for addr_reg in self.get_all_registers():
        if addr_reg == jump_reg: continue

        # Find a gadget to read from memory
        read_gadget = self.find_gadget(ga.LoadMem, input_registers = [addr_reg], output_register = jump_reg)
        if read_gadget == None:
          continue

        # Then find a gadget that will let you set the address register for that read
        set_read_addr_gadget = self.find_load_stack_gadget(read_gadget.inputs[0], [jump_reg])
        if set_read_addr_gadget == None:
          continue
        break

      if set_read_addr_gadget == None or read_gadget == None:
        continue

      # Then find a gadget that will let you jump to that register
      jump_gadget = self.find_gadget(ga.Jump, [jump_reg])
      if jump_gadget == None:
        continue

      add_jump_reg_gadget = set_add_reg_gadget = None
      for add_reg in self.get_all_registers():
        offset = original_offset
        if add_reg == jump_reg: continue

        # Then find a gadget that will let you add to that register
        add_jump_reg_gadget = self.find_gadget(ga.AddGadget, [jump_reg, add_reg], jump_reg)
        if add_jump_reg_gadget == None: # If we can't find an AddGadget, try finding a SubGadget and negating
          add_jump_reg_gadget = self.find_gadget(ga.SubGadget, [jump_reg, add_reg], jump_reg)
          offset = -offset
          if add_jump_reg_gadget == None:
            continue

        # Next, find a gadget that will let you set what you're adding to that register
        set_add_reg_gadget = self.find_load_stack_gadget(add_reg, [jump_reg])
        if set_add_reg_gadget == None:
          continue
        break

      if add_jump_reg_gadget == None:
        continue

      # last, find gadgets to set each of the arguments while avoiding clobbering our jump register
      arg_gadgets = []
      no_clobber = [jump_reg]
      for i in range(len(arguments)):
        reg = self.reg_number(self.func_calling_convention[self.arch.name][i])
        arg_gadget = self.find_load_stack_gadget(reg, no_clobber)
        if arg_gadget != None:
          arg_gadgets.append(arg_gadget)
        no_clobber.append(reg)

      if len(arg_gadgets) == len(arguments) and (
          read_gadget.stack_offset + set_read_addr_gadget.stack_offset + jump_gadget.stack_offset +
          add_jump_reg_gadget.stack_offset + set_add_reg_gadget.stack_offset +
          sum([x.stack_offset for x in arg_gadgets])
        ) < 0x1000:
        break
      arg_gadgets = []

    # Couldn't find all the necessary gadgets
    if len(arg_gadgets) != len(arguments):
      return (None, None)

    self.logger.debug("Found all necessary gadgets for reading the GOT and calling a different function:")
    for gadget in [set_read_addr_gadget, read_gadget, set_add_reg_gadget, add_jump_reg_gadget, arg_gadgets[0], arg_gadgets[1], arg_gadgets[2], jump_gadget]:
      self.logger.debug(gadget)

    # Start building the chain
    start_of_function_address = jump_gadget.address
    if len(arg_gadgets) > 0:
      start_of_function_address = arg_gadgets[0].address

    chain = set_read_addr_gadget.chain(read_gadget.address, address - read_gadget.params[0]) # set the read address
    chain += read_gadget.chain(set_add_reg_gadget.address)                                   # read the address in the GOT
    chain += set_add_reg_gadget.chain(add_jump_reg_gadget.address, offset)                   # set the offset from the base to the target
    chain += add_jump_reg_gadget.chain(start_of_function_address)                            # add the offset

    # Set the arguments for the function
    for i in range(len(arg_gadgets)):
      next_address = jump_gadget.address
      if i + 1 < len(arguments):
        next_address = arg_gadgets[i + 1].address
      chain += arg_gadgets[i].chain(next_address, arguments[i])

    # Finally, jump to the function
    chain += jump_gadget.chain()
    chain += self.ap(end_address)
    return (chain, set_read_addr_gadget.address)

  def create_shellcode_address_chain(self, goal):
    """This method returns a ROP chain for a ShellcodeAddressGoal.  The ROP will fix the memory permissions and then jump to the
      shellcode's address."""

    # Look for the address of functions capable of fixing the memory protections
    addresses = self.goal_resolver.resolve_functions(["mprotect", "syscall"])

    if addresses["mprotect"] != None:
      # If we've have mprotect, we're on easy street.  Create a chain to call mprotect()
      self.logger.info("Found mprotect, using to change shellcode permissions")
      mprotect_goal = go.FunctionGoal("mprotect", addresses["mprotect"], [goal.shellcode_address & PAGE_MASK, 0x1000, PROT_RWX])
      return self.create_function_chain(mprotect_goal, goal.shellcode_address)
    elif addresses["syscall"] != None:
      # If we've have the syscall function, slightly harder as it needs an extra argument. Create a chain to call syscall()
      self.logger.info("Found syscall(), using it to call mprotect to change shellcode permissions")
      syscall_goal = go.FunctionGoal("syscall", addresses["syscall"], [MPROTECT_SYSCALL, goal.shellcode_address & PAGE_MASK, 0x1000, PROT_RWX])
      return self.create_function_chain(syscall_goal, goal.shellcode_address)

    # TODO add mmap/memcpy, mmap + rop memory writing, using syscalls instead of functions, and others ways to fix the memory protections

    # We failed using the easy techniques for fixing memory, so now try to read the GOT address for a used function and then add
    # the offset in libc to find mprotect.  This will allow us to call mprotect without knowing the address of libc
    self.logger.info("Couldn't find mprotect or syscall, restorting to reading the GOT and computing addresses")
    functions_in_got = ["printf", "puts", "read", "open", "close", "exit"] # Keep trying, in case they don't use the first function
    base_address_in_got = offset_in_libc = None
    for base in functions_in_got:
      # Find the address of the base function in libc, and the offset between it and mprotect
      base_address_in_got, offset_in_libc = self.goal_resolver.resolve_symbol_from_got(base, "mprotect")
      if base_address_in_got != None and offset_in_libc != None:
        self.logger.info("Used %s to found the address of libc: 0x%x", base, base_address_in_got)
        break

    if base_address_in_got != None and offset_in_libc != None:
      # Create the chain to call mprotect based on the base function's address
      mprotect_args = [goal.shellcode_address & PAGE_MASK, 0x2000, PROT_RWX]
      chain, next_address = self.create_read_add_jmp_function_chain(base_address_in_got, offset_in_libc, mprotect_args, goal.shellcode_address)
      if chain != None:
        return chain, next_address

    raise RuntimeError("Failed finding necessary gadgets for shellcode address goal")

  def create_write_memory_chain(self, buf, address, next_address):
    """This method generates a chain that will write the buffer to the given address.  Similar to ROPC we limit ourselves to one
      memory size for simplicity.  Thus, the buffer must be arch.bits/8 bytes long"""
    if len(buf) != (self.arch.bits/8):
      raise RuntimeError("Write memory chains can only write memory in chunks of %d bytes, requested %d" % (self.arch.bits/8, len(buf)))

    # First find the necessary gagdgets
    load_addr_gadget, load_value_gadget, store_mem_gadget = self.get_write_memory_gadget()

    # Next create the chain to setup the address and value to be written
    chain = load_addr_gadget.chain(load_value_gadget.address, address)
    chain += load_value_gadget.chain(store_mem_gadget.address, buf)

    # Finally, create the chain to write to memory
    chain += store_mem_gadget.chain(next_address)

    return (chain, load_addr_gadget.address)

  def create_write_shellcode_chain(self, shellcode, address, next_address):
    """This function returns a ROP chain implemented to write shellcode to a given address"""
    alignment = self.arch.bits / 8
    if len(shellcode) % alignment != 0:
      shellcode += (alignment - (len(shellcode) % alignment)) * "K" # pad it to the correct alignment (for simplicity)

    chain = ""
    addr = address
    for i in range(0, len(shellcode), alignment):
      # Iteratively create the ROP chain for each byte chunk of the shellcode
      single_write_chain, next_address = self.create_write_memory_chain(shellcode[i:i+alignment], addr, next_address)
      chain = single_write_chain + chain
      addr += alignment
    return chain, next_address

  def create_shellcode_chain(self, goal):
    """This function returns a ROP chain implemented for a ShellcodeGoal.  It first writes the given shellcode to memory,
      then creates a ShellcodeAddressGoal and adds its ROP chain on."""
    shellcode_address = self.goal_resolver.get_writable_memory()
    self.find_write_memory_gadgets()

    # Create a ROP chain that will fix memory permissions and jump to our shellcode
    shellcode_goal = go.ShellcodeAddressGoal(shellcode_address)
    shellcode_chain, next_address = self.create_shellcode_address_chain(shellcode_goal)

    # Create a ROP chain that will write our shellcode to memory
    chain, next_address = self.create_write_shellcode_chain(goal.shellcode, shellcode_address, next_address)

    # Combine the two to write our shellcode to memory and execute it
    return (chain + shellcode_chain), next_address

  def chain_gadgets(self):
    """This function returns a ROP chain implemented for the given goals."""
    chain = ""
    next_address = 0x4444444444444444
    for i in range(len(self.goals)-1, -1, -1):
      goal = self.goals[i]
      if type(goal) == go.FunctionGoal:
        goal_chain, next_address = self.create_function_chain(goal, next_address)
        self.logger.debug("Function call to %s's first gadget is at 0x%x", goal.name, next_address)
      elif type(goal) == go.ShellcodeAddressGoal:
        goal_chain, next_address = self.create_shellcode_address_chain(goal)
      elif type(goal) == go.ShellcodeGoal:
        goal_chain, next_address = self.create_shellcode_chain(goal)

      chain = goal_chain + chain

    return self.ap(next_address) + chain


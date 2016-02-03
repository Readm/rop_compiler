from elftools.elf.elffile import ELFFile
from elftools.elf.constants import P_FLAGS
import archinfo
import logging, collections

import classifier as cl, gadget as ga

class Finder(object):
  """This class parses an ELF files to obtain any gadgets inside their executable sections"""

  """The maximum size in bytes of a gadget to look for"""
  MAX_GADGET_SIZE = { archinfo.ArchX86 : 10, archinfo.ArchAMD64 : 10, archinfo.ArchMIPS64 : 20, archinfo.ArchMIPS32 : 20,
    archinfo.ArchPPC32 : 20, archinfo.ArchPPC64 : 20, archinfo.ArchARM : 20 }

  """A list containing any instructions which signify the end of a gadget."""
  GADGET_END_INSTRUCTIONS = ['ret', 'jmp']

  """The amount to step between instructions"""
  STEP = { archinfo.ArchX86 : 1, archinfo.ArchAMD64 : 1, archinfo.ArchMIPS64 : 4, archinfo.ArchMIPS32 : 4,
    archinfo.ArchPPC32 : 4, archinfo.ArchPPC64 : 4, archinfo.ArchARM : 4 }

  def __init__(self, filename, gadget_file, arch, base_address = 0, level = logging.WARNING):
    logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    self.logger = logging.getLogger(self.__class__.__name__)
    self.logger.setLevel(level)
    self.level = level

    self.base_address = base_address
    self.arch = arch

    self.elffile = self.fd = None
    if filename != None:
      self.fd = open(filename, "rb")
      self.elffile = ELFFile(self.fd)

    self.gadget_file_fd = None
    if gadget_file != None:
      self.gadget_file_fd = open(gadget_file, "rb")

  def __del__(self):
    if self.fd != None:
      self.fd.close()
    if self.gadget_file_fd != None:
      self.gadget_file_fd.close()

  def find_gadgets(self):
    """Iterates over the defined files and return any gadgets"""
    if self.gadget_file_fd != None: # there is a saved gadgets file
      gadget_list = ga.from_string(self.gadget_file_fd.read(), self.level, self.base_address)
    else: # No gadget file, try to find them
      gadget_list = ga.GadgetList(log_level = self.level)
      for segment in self.iter_executable_segments():
        self.get_gadgets_for_segment(segment, gadget_list)
    self.logger.debug("Found %d (%d LoadMem) gadgets", len([x for x in gadget_list.foreach()]), len([x for x in gadget_list.foreach_type(ga.LoadMem)]))
    return gadget_list

  def iter_executable_segments(self):
    """Any iterator that only returns the executable sections in the ELF file"""
    for seg in self.elffile.iter_segments():
      if seg.header.p_flags & P_FLAGS.PF_X != 0:
        yield seg

  def get_gadgets_for_segment(self, segment, gadget_list):
    """Iteratively step through an executable section looking for gadgets at each address"""
    if self.base_address == 0 and segment.header.p_paddr == 0: # libraries and PIE executable, don't have the p_paddr in the header set to 0
      self.logger.warning("No base address given for library or PIE executable.  Addresses may be wrong")

    classifier = cl.GadgetClassifier(self.arch, self.level)
    data = segment.data()
    for i in range(0, len(data), self.STEP[self.arch]):
      end = i + self.MAX_GADGET_SIZE[self.arch]
      code = data[i:end]
      address = self.base_address + segment.header.p_paddr + i
      gadget_list.add_gadgets(classifier.create_gadgets_from_instructions(code, address))

if __name__ == "__main__":
  import argparse

  parser = argparse.ArgumentParser(description="Run the gadget locator on the supplied binary")
  parser.add_argument('-target', type=str, default=None, help='The file (executable/library) to find gadgets in')
  parser.add_argument('-gadgets_file', type=str, default=None, help='The file (executable/library) to find gadgets in')
  parser.add_argument('-base_address', type=str, default="0", help='The address the file is loaded at (in hex). Only needed'
    + ' for PIE/PIC binaries.  When creating a reusable gadgets file, do not specify')
  parser.add_argument('-arch', type=str, default="AMD64", help='The architecture of the binary')
  parser.add_argument('-v', required=False, action='store_true', help='Verbose mode')
  parser.add_argument('-o', type=str, default=None, help='File to write the gadgets to')
  args = parser.parse_args()

  finder = Finder(args.target, args.gadgets_file, archinfo.arch_from_id(args.arch).__class__, int(args.base_address, 16), logging.DEBUG if args.v else logging.WARNING)
  gadget_list = finder.find_gadgets()

  if args.o == None:
    for gadget in gadget_list.foreach():
      print gadget, gadget.complexity()
  else:
    fd = open(args.o, "w")
    fd.write(gadget_list.to_string())
    fd.close()


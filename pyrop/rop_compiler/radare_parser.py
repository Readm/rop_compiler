import logging, collections, os
import file_parser
from r2 import r_bin

class RadareFinder(file_parser.FileParser):
  """This class parses an executable file using radare"""

  def __init__(self, filename, base_address = 0, level = logging.WARNING):
    super(RadareFinder, self).__init__(filename, base_address, level)

    io = r_bin.RIO()
    self.desc = io.open(filename, 0, 0)
    if self.desc == None:
      msg = "Could not open %s", filename
      self.logger.critical(msg)
      raise RuntimeError(msg)
    self.fd = open(filename, "r")

    self.b = r_bin.RBin()
    self.b.iobind(io)
    self.b.load(filename, 0, 0, 0, self.desc.fd, False)
    self.baddr = self.b.get_baddr()

  def __del__(self):
    self.fd.close()

  def iter_executable_segments(self):
    """Any iterator that only returns the executable sections in the ELF file"""
    EXECUTABLE = 1
    for seg in self.b.get_sections():
      if seg.srwx & EXECUTABLE != 0:
        yield seg

  def get_segment_bytes_address(self, seg):
    """Returns a segments bytes and the address of the segment"""
    self.fd.seek(seg.paddr)
    return self.fd.read(seg.size), seg.vaddr

  def get_symbol_address(self, name, recurse_with_imp = True):
    """Returns the address for a symbol, or None if the symbol can't be found"""
    for symbol in self.b.get_symbols():
      if symbol.name == name:
        return int(symbol.vaddr)
    if recurse_with_imp:
      return self.get_symbol_address("imp.{}".format(name), False)
    return None

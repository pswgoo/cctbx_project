from __future__ import generators
from cctbx.array_family import flex

import boost.python
ext = boost.python.import_ext("iotbx_pdb_ext")
from iotbx_pdb_ext import *

import iotbx.pdb.records
import iotbx.pdb.hierarchy

from iotbx.pdb.atom_name_interpretation import \
  interpreters as protein_atom_name_interpreters
import scitbx.array_family.shared
import scitbx.stl.set
from libtbx import smart_open
from libtbx.math_utils import iround
from libtbx.str_utils import show_string, show_sorted_by_counts
from libtbx.utils import plural_s, Sorry, hashlib_md5, date_and_time
from libtbx import Auto
import sys

def is_pdb_file(file_name):
  for pdb_str in open(file_name):
    if (pdb_str.startswith("CRYST1")):
      try: cryst1 = iotbx.pdb.records.cryst1(pdb_str=pdb_str)
      except iotbx.pdb.records.FormatError: continue
      if (cryst1.ucparams is not None and cryst1.sgroup is not None):
        return True
    elif (   pdb_str.startswith("ATOM  ")
          or pdb_str.startswith("HETATM")):
      try: pdb_inp = ext.input(
        source_info=None, lines=flex.std_string([pdb_str]))
      except KeyboardInterrupt: raise
      except: continue
      if (pdb_inp.atoms().size() == 1):
        atom = pdb_inp.atoms()[0]
        if (atom.name != "    "):
          return True
  return False

cns_dna_rna_residue_names = {
  "ADE": "A",
  "CYT": "C",
  "GUA": "G",
  "THY": "T",
  "URI": "U"
}

mon_lib_dna_rna_cif = ["AD", "AR", "CD", "CR", "GD", "GR", "TD", "UR"]
if ("set" in __builtins__):
  mon_lib_dna_rna_cif = set(mon_lib_dna_rna_cif)

rna_dna_reference_residue_names = {
  "A": "?A",
  "C": "?C",
  "G": "?G",
  "U": "U",
  "T": "DT",
  "+A": "?A",
  "+C": "?C",
  "+G": "?G",
  "+U": "U",
  "+T": "DT",
  "DA": "DA",
  "DC": "DC",
  "DG": "DG",
  "DT": "DT",
  "ADE": "?A",
  "CYT": "?C",
  "GUA": "?G",
  "URI": "U",
  "THY": "DT",
  "AR": "A",
  "CR": "C",
  "GR": "G",
  "UR": "U",
  "AD": "DA",
  "CD": "DC",
  "GD": "DG",
  "TD": "DT"
}

def rna_dna_reference_residue_name(common_name):
  return rna_dna_reference_residue_names.get(common_name.strip().upper())

rna_dna_atom_names_reference_to_mon_lib_translation_dict = {
  " C1'": "C1*",
  " C2 ": "C2",
  " C2'": "C2*",
  " C3'": "C3*",
  " C4 ": "C4",
  " C4'": "C4*",
  " C5 ": "C5",
  " C5'": "C5*",
  " C6 ": "C6",
  " C7 ": "C5M",
  " C8 ": "C8",
  " H1 ": "H1",
  " H1'": "H1*",
  " H2 ": "H2",
# " H2'": special case: rna: "H2*", dna: "H2*1"
  " H21": "H21",
  " H22": "H22",
  " H3 ": "H3",
  " H3'": "H3*",
  " H4'": "H4*",
  " H41": "H41",
  " H42": "H42",
  " H5 ": "H5",
  " H5'": "H5*1",
  " H6 ": "H6",
  " H61": "H61",
  " H62": "H62",
  " H71": "H5M1",
  " H72": "H5M2",
  " H73": "H5M3",
  " H8 ": "H8",
  " N1 ": "N1",
  " N2 ": "N2",
  " N3 ": "N3",
  " N4 ": "N4",
  " N6 ": "N6",
  " N7 ": "N7",
  " N9 ": "N9",
  " O2 ": "O2",
  " O2'": "O2*",
  " O3'": "O3*",
  " O4 ": "O4",
  " O4'": "O4*",
  " O5'": "O5*",
  " O6 ": "O6",
  " OP1": "O1P",
  " OP2": "O2P",
  " OP3": "O3T",
  " P  ": "P",
  "H2''": "H2*2",
  "H5''": "H5*2",
  "HO2'": "HO2*",
  "HO3'": "HO3*",
  "HO5'": "HO5*"
# "HOP3": not covered by monomer library
}

class rna_dna_atom_names_interpretation(object):

  def __init__(self, residue_name, atom_names):
    if (residue_name == "T"):
      residue_name = "DT"
    else:
      assert residue_name in ["?A", "?C", "?G",
                              "A", "C", "G", "U",
                              "DA", "DC", "DG", "DT", "T"]
    self.residue_name = residue_name
    self.atom_names = atom_names
    rna_dna_atom_names_interpretation_core(self)

  def unexpected_atom_names(self):
    result = []
    for atom_name,info in zip(self.atom_names, self.infos):
      if (info.reference_name is None):
        result.append(atom_name)
    return result

  def mon_lib_names(self):
    result = []
    for info in self.infos:
      rn = info.reference_name
      if (rn is None):
        result.append(None)
      else:
        mn = rna_dna_atom_names_reference_to_mon_lib_translation_dict.get(rn)
        if (mn is not None):
          result.append(mn)
        elif (rn == " H2'"):
          if (self.residue_name.startswith("D")):
            result.append("H2*1")
          else:
            result.append("H2*")
        else:
          assert rn == "HOP3" # only atom not covered by monomer library
          result.append(None)
    return result

class residue_name_plus_atom_names_interpreter(object):

  def __init__(self,
        residue_name,
        atom_names,
        translate_cns_dna_rna_residue_names=None,
        return_mon_lib_dna_name=False):
    work_residue_name = residue_name.strip().upper()
    if (len(work_residue_name) == 0):
      self.work_residue_name = None
      self.atom_name_interpretation = None
      return
    protein_interpreter = protein_atom_name_interpreters.get(work_residue_name)
    atom_name_interpretation = None
    if (protein_interpreter is not None):
      atom_name_interpretation = protein_interpreter.match_atom_names(
        atom_names=atom_names)
    else:
      if (    translate_cns_dna_rna_residue_names is not None
          and not translate_cns_dna_rna_residue_names
          and work_residue_name in cns_dna_rna_residue_names):
        rna_dna_ref_residue_name = None
      else:
        rna_dna_ref_residue_name = rna_dna_reference_residue_name(
          common_name=work_residue_name)
      if (rna_dna_ref_residue_name is not None):
        atom_name_interpretation = rna_dna_atom_names_interpretation(
          residue_name=rna_dna_ref_residue_name,
          atom_names=atom_names)
        if (atom_name_interpretation.n_unexpected != 0):
          if (    len(atom_names) == 1
              and work_residue_name in mon_lib_dna_rna_cif):
            self.work_residue_name = None
            self.atom_name_interpretation = None
            return
          if (    translate_cns_dna_rna_residue_names is None
              and work_residue_name in cns_dna_rna_residue_names):
            atom_name_interpretation = None
        if (atom_name_interpretation is not None):
          work_residue_name = atom_name_interpretation.residue_name
          if (return_mon_lib_dna_name):
            work_residue_name = {
              "A": "AR",
              "C": "CR",
              "G": "GR",
              "U": "UR",
              "DA": "AD",
              "DC": "CD",
              "DG": "GD",
              "DT": "TD"}[work_residue_name]
    self.work_residue_name = work_residue_name
    self.atom_name_interpretation = atom_name_interpretation

class combine_unique_pdb_files(object):

  def __init__(self, file_names):
    self.file_name_registry = {}
    self.md5_registry = {}
    self.unique_file_names = []
    self.raw_records = []
    for file_name in file_names:
      if (file_name in self.file_name_registry):
        self.file_name_registry[file_name] += 1
      else:
        self.file_name_registry[file_name] = 1
        r = [s.expandtabs().rstrip()
          for s in smart_open.for_reading(
            file_name=file_name).read().splitlines()]
        m = hashlib_md5()
        m.update("\n".join(r))
        m = m.hexdigest()
        l = self.md5_registry.get(m)
        if (l is not None):
          l.append(file_name)
        else:
          self.md5_registry[m] = [file_name]
          self.unique_file_names.append(file_name)
          self.raw_records.extend(r)

  def report_non_unique(self, out=None, prefix=""):
    if (out is None): out = sys.stdout
    n_ignored = 0
    for file_name in sorted(self.file_name_registry.keys()):
      n = self.file_name_registry[file_name]
      if (n != 1):
        print >> out, prefix+"INFO: PDB file name appears %d times: %s" % (
          n, show_string(file_name))
        n_ignored += (n-1)
    if (n_ignored != 0):
      print >> out, prefix+"  %d repeated file name%s ignored." % \
        plural_s(n=n_ignored)
    n_identical = 0
    for file_names in self.md5_registry.values():
      if (len(file_names) != 1):
        print >> out, prefix+"INFO: PDB files with identical content:"
        for file_name in file_names:
          print >> out, prefix+"  %s" % show_string(file_name)
        n_identical += len(file_names)-1
    if (n_identical != 0):
      print >> out, prefix+"%d file%s with repeated content ignored." % \
        plural_s(n=n_identical)
    if (n_ignored != 0 or n_identical != 0):
      print >> out, prefix.rstrip()

class header_date:

  def __init__(self, field):
    "Expected format: DD-MMM-YY"
    self.dd = None
    self.mmm = None
    self.yy = None
    if (len(field) != 9): return
    if (field.count("-") != 2): return
    if (field[2] != "-" or field[6] != "-"): return
    dd, mmm, yy = field.split("-")
    try: self.dd = int(dd)
    except ValueError: pass
    else:
      if (self.dd < 1 or self.dd > 31): self.dd = None
    if (mmm.upper() in [
          "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
          "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]):
      self.mmm = mmm.upper()
    try: self.yy = int(yy)
    except ValueError: pass
    else:
      if (self.yy < 0 or self.yy > 99): self.yy = None

  def is_fully_defined(self):
    return self.dd is not None \
       and self.mmm is not None \
       and self.yy is not None

def header_year(record):
  if (record.startswith("HEADER")):
    date = header_date(field=record[50:59])
    if (date.is_fully_defined()): return date.yy
    fields = record.split()
    fields.reverse()
    for field in fields:
      date = header_date(field=field)
      if (date.is_fully_defined()): return date.yy
  return None

class Please_pass_string_or_None(object): pass

def input(
    file_name=None,
    source_info=Please_pass_string_or_None,
    lines=None):
  if (file_name is not None):
    return ext.input(
      source_info="file " + file_name,
      lines=flex.split_lines(smart_open.for_reading(file_name).read()))
  assert source_info is not Please_pass_string_or_None
  if (isinstance(lines, str)):
    lines = flex.split_lines(lines)
  elif (isinstance(lines, (list, tuple))):
    lines = flex.std_string(lines)
  return ext.input(source_info=source_info, lines=lines)

default_atom_names_scattering_type_const = ["PEAK", "SITE"]

class _input(boost.python.injector, ext.input):

  def atoms_with_labels(self):
    model_ids = self.model_ids()
    if (model_ids.size() == 0):
      return
    model_id = model_ids[0]
    m = self.model_indices()
    c = self.chain_indices()
    b = self.break_indices()
    m_i = m[0]
    c_i = c[0][0]
    if (len(b) != 0): b_i = b[0]
    else:             b_i = -1
    i_m = 0
    i_c = 0
    i_b = 0
    i_a = 0
    atom_with_labels = iotbx.pdb.hierarchy.atom_with_labels
    for lbls,atom in zip(self.input_atom_labels_list(), self.atoms()):
      if (i_a == m_i):
        i_m += 1
        model_id = model_ids[i_m]
        m_i = m[i_m]
        c_i = c[i_m][0]
        is_first_in_chain = True
      elif (i_a == 0):
        is_first_in_chain = True
      else:
        is_first_in_chain = (i_a == c_i)
        if (is_first_in_chain):
          i_c += 1
          c_i = c[i_m][i_c]
      is_first_after_break = (i_a == b_i)
      if (is_first_after_break):
        i_b += 1
        if (i_b != len(b)):
          b_i = b[i_b]
      yield atom_with_labels(
        atom=atom,
        model_id=model_id,
        chain_id=lbls.chain(),
        resseq=lbls.resseq(),
        icode=lbls.icode(),
        altloc=lbls.altloc(),
        resname=lbls.resname(),
        is_first_in_chain=is_first_in_chain,
        is_first_after_break=is_first_after_break)
      i_a += 1

  def extract_header_year(self):
    for line in self.title_section():
      if (line.startswith("HEADER ")):
        return header_year(line)
    return None

  def extract_remark_iii_records(self, iii):
    result = []
    pattern = "REMARK %3d " % iii
    for line in self.remark_section():
      if (line.startswith(pattern)):
        result.append(line)
    return result

  def crystal_symmetry_from_cryst1(self):
    from iotbx.pdb import cryst1_interpretation
    for line in self.crystallographic_section():
      if (line.startswith("CRYST1")):
        return cryst1_interpretation.crystal_symmetry(cryst1_record=line)
    return None

  def crystal_symmetry_from_cns_remark_sg(self):
    from iotbx.cns import pdb_remarks
    for line in self.remark_section():
      if (line.startswith("REMARK sg=")):
        crystal_symmetry = pdb_remarks.extract_symmetry(pdb_record=line)
        if (crystal_symmetry is not None):
          return crystal_symmetry
    return None

  def crystal_symmetry(self,
        crystal_symmetry=None,
        weak_symmetry=False):
    self_symmetry = self.crystal_symmetry_from_cryst1()
    if (self_symmetry is None):
      self_symmetry = self.crystal_symmetry_from_cns_remark_sg()
    if (crystal_symmetry is None):
      return self_symmetry
    if (self_symmetry is None):
      return crystal_symmetry
    return self_symmetry.join_symmetry(
      other_symmetry=crystal_symmetry,
      force=not weak_symmetry)

  def special_position_settings(self,
        special_position_settings=None,
        weak_symmetry=False,
        min_distance_sym_equiv=0.5,
        u_star_tolerance=0):
    crystal_symmetry = self.crystal_symmetry(
      crystal_symmetry=special_position_settings,
      weak_symmetry=weak_symmetry)
    if (crystal_symmetry is None): return None
    if (special_position_settings is not None):
      min_distance_sym_equiv=special_position_settings.min_distance_sym_equiv()
      u_star_tolerance = special_position_settings.u_star_tolerance()
    return crystal_symmetry.special_position_settings(
      min_distance_sym_equiv=min_distance_sym_equiv,
      u_star_tolerance=u_star_tolerance)

  def scale_matrix(self):
    if (not hasattr(self, "_scale_matrix")):
      source_info = self.source_info()
      if (len(source_info) > 0): source_info = " (%s)" % source_info
      self._scale_matrix = [[None]*9,[None]*3]
      done = {}
      for line in self.crystallographic_section():
        if (line.startswith("SCALE") and line[5:6] in ["1", "2", "3"]):
          r = read_scale_record(line=line, source_info=source_info)
          for i_col,v in enumerate([r.sn1, r.sn2, r.sn3]):
            self._scale_matrix[0][(r.n-1)*3+i_col] = v
          self._scale_matrix[1][r.n-1] = r.un
          done[r.n] = None
      done = done.keys()
      done.sort()
      if (len(done) == 0):
        self._scale_matrix = None
      elif (done != [1,2,3]):
        raise RuntimeError(
          "Incomplete set of PDB SCALE records%s" % source_info)
    return self._scale_matrix

  def xray_structure_simple(self,
        crystal_symmetry=None,
        weak_symmetry=False,
        unit_cube_pseudo_crystal=False,
        fractional_coordinates=False,
        use_scale_matrix_if_available=True,
        min_distance_sym_equiv=0.5,
        scattering_type_exact=False,
        enable_scattering_type_unknown=False,
        atom_names_scattering_type_const
          =default_atom_names_scattering_type_const):
    return self.xray_structures_simple(
      one_structure_for_each_model=False,
      crystal_symmetry=crystal_symmetry,
      weak_symmetry=weak_symmetry,
      unit_cube_pseudo_crystal=unit_cube_pseudo_crystal,
      fractional_coordinates=fractional_coordinates,
      use_scale_matrix_if_available=use_scale_matrix_if_available,
      min_distance_sym_equiv=min_distance_sym_equiv,
      scattering_type_exact=scattering_type_exact,
      enable_scattering_type_unknown=enable_scattering_type_unknown,
      atom_names_scattering_type_const=atom_names_scattering_type_const)[0]

  def xray_structures_simple(self,
        one_structure_for_each_model=True,
        crystal_symmetry=None,
        weak_symmetry=False,
        unit_cube_pseudo_crystal=False,
        fractional_coordinates=False,
        min_distance_sym_equiv=0.5,
        use_scale_matrix_if_available=True,
        scattering_type_exact=False,
        enable_scattering_type_unknown=False,
        atom_names_scattering_type_const
          =default_atom_names_scattering_type_const):
    from cctbx import xray
    from cctbx import crystal
    assert crystal_symmetry is None or not unit_cube_pseudo_crystal
    if (not unit_cube_pseudo_crystal):
      crystal_symmetry = self.crystal_symmetry(
        crystal_symmetry=crystal_symmetry,
        weak_symmetry=weak_symmetry)
    if (crystal_symmetry is None
        or (    crystal_symmetry.unit_cell() is None
            and crystal_symmetry.space_group_info() is None)):
      unit_cube_pseudo_crystal = True
      crystal_symmetry = crystal.symmetry(
        unit_cell=(1,1,1,90,90,90),
        space_group_symbol="P1")
    assert crystal_symmetry.unit_cell() is not None
    assert crystal_symmetry.space_group_info() is not None
    unit_cell = crystal_symmetry.unit_cell()
    scale_r = (0,0,0,0,0,0,0,0,0)
    scale_t = (0,0,0)
    if (not unit_cube_pseudo_crystal):
      if (use_scale_matrix_if_available):
        scale_matrix = self.scale_matrix()
        if (scale_matrix is not None):
          # Avoid subtle inconsistencies due to rounding errors.
          # 1.e-6 is the precision of the values on the SCALE records.
          if (max([abs(s-f) for s,f in zip(
                     scale_matrix[0],
                     unit_cell.fractionalization_matrix())]) < 1.e-6):
            if (scale_matrix[1] != [0,0,0]):
              scale_matrix[0] = unit_cell.fractionalization_matrix()
            else:
              scale_matrix = None
      else:
        scale_matrix = None
      if (scale_matrix is not None):
        scale_r = scale_matrix[0]
        scale_t = scale_matrix[1]
    result = []
    if (atom_names_scattering_type_const is None):
      atom_names_scattering_type_const = []
    loop = xray_structures_simple_extension(
      self,
      one_structure_for_each_model,
      unit_cube_pseudo_crystal,
      fractional_coordinates,
      scattering_type_exact,
      enable_scattering_type_unknown,
      scitbx.stl.set.stl_string(atom_names_scattering_type_const),
      unit_cell,
      scale_r,
      scale_t)
    special_position_settings = crystal_symmetry.special_position_settings(
      min_distance_sym_equiv=min_distance_sym_equiv)
    while (loop.next()):
      result.append(xray.structure(
        special_position_settings=special_position_settings,
        scatterers=loop.scatterers))
    return result

class rewrite_normalized(object):

  def __init__(self,
        input_file_name,
        output_file_name,
        keep_original_crystallographic_section=False,
        keep_original_atom_serial=False):
    self.input = input(file_name=input_file_name)
    if (keep_original_crystallographic_section):
      print >> open(output_file_name, "wb"), \
        "\n".join(self.input.crystallographic_section())
      crystal_symmetry = None
    else:
      crystal_symmetry = self.input.crystal_symmetry()
    self.hierarchy = self.input.construct_hierarchy()
    if (not keep_original_atom_serial):
      self.hierarchy.atoms().reset_serial()
    self.hierarchy.write_pdb_file(
      file_name=output_file_name,
      open_append=keep_original_crystallographic_section,
      append_end=True,
      crystal_symmetry=crystal_symmetry)

# Table of structures split into multiple PDB files.
# Assembled manually.
# Based on 46377 PDB files as of Tuesday Oct 02, 2007
#   noticed in passing: misleading REMARK 400 in 1VSA (1vs9 and 2i1c
#   don't exist)
pdb_codes_fragment_files = """\
1pns 1pnu
1pnx 1pny
1s1h 1s1i
1ti2 1vld
1ti4 1vle
1ti6 1vlf
1voq 1vor 1vos 1vou 1vov 1vow 1vox 1voy 1voz 1vp0
1vs5 1vs6 1vs7 1vs8
1vsa 2ow8
1yl3 1yl4
2avy 2aw4 2aw7 2awb
2b64 2b66
2b9m 2b9n
2b9o 2b9p
2gy9 2gya
2gyb 2gyc
2hgi 2hgj
2hgp 2hgq
2hgr 2hgu
2i2p 2i2t 2i2u 2i2v
2qal 2qam 2qan 2qao
2qb9 2qba 2qbb 2qbc
2qbd 2qbe 2qbf 2qbg
2qbh 2qbi 2qbj 2qbk
2qou 2qov 2qow 2qox
2qoy 2qoz 2qp0 2qp1
2z4k 2z4l 2z4m 2z4n
"""

def join_fragment_files(file_names):
  info = flex.std_string()
  info.append("REMARK JOINED FRAGMENT FILES (iotbx.pdb)")
  info.append("REMARK " + date_and_time())
  roots = []
  cryst1 = Auto
  sum_z = None
  z_warning = 'REMARK ' \
    'Warning: CRYST1 Z field (columns 67-70) is not an integer: "%-4.4s"'
  for file_name in file_names:
    info.append("REMARK %s" % show_string(file_name))
    pdb_inp = iotbx.pdb.input(file_name=file_name)
    roots.append(pdb_inp.construct_hierarchy())
    c1s = []
    for line in pdb_inp.crystallographic_section():
      if (line.startswith("CRYST1")):
        info.append("REMARK %s" % line.rstrip())
        c1s.append(line)
        if (cryst1 is Auto):
          cryst1 = line[:66]
          try: sum_z = int(line[66:70])
          except ValueError:
            info.append(z_warning % line[66:70])
            sum_z = None
        elif (cryst1 is not None and line[:66] != cryst1):
          info.append("REMARK Warning: CRYST1 mismatch.")
          cryst1 = None
          sum_z = None
        elif (sum_z is not None):
          try: sum_z += int(line[66:70])
          except ValueError:
            info.append(z_warning % line[66:70])
            sum_z = None
    if (len(c1s) == 0):
      info.append("REMARK Warning: CRYST1 record not available.")
      sum_z = None
    elif (len(c1s) > 1):
      info.append("REMARK Warning: Multiple CRYST1 records.")
      sum_z = None
  if (cryst1 is not Auto and cryst1 is not None):
    if (sum_z is not None):
      cryst1 = "%-66s%4d" % (cryst1, sum_z)
    info.append(cryst1.rstrip())
  result = iotbx.pdb.hierarchy.join_roots(roots=roots)
  result.info.extend(info)
  return result

def format_cryst1_record(crystal_symmetry, z=None):
  # CRYST1
  #  7 - 15       Real(9.3)      a             a (Angstroms).
  # 16 - 24       Real(9.3)      b             b (Angstroms).
  # 25 - 33       Real(9.3)      c             c (Angstroms).
  # 34 - 40       Real(7.2)      alpha         alpha (degrees).
  # 41 - 47       Real(7.2)      beta          beta (degrees).
  # 48 - 54       Real(7.2)      gamma         gamma (degrees).
  # 56 - 66       LString        sGroup        Space group.
  # 67 - 70       Integer        z             Z value.
  if (z is None): z = ""
  else: z = str(z)
  return ("CRYST1%9.3f%9.3f%9.3f%7.2f%7.2f%7.2f %-11.11s%4.4s" % (
    crystal_symmetry.unit_cell().parameters()
    + (str(crystal_symmetry.space_group_info()), z))).rstrip()

def format_scale_records(unit_cell=None,
                         fractionalization_matrix=None,
                         u=[0,0,0]):
  #  1 -  6       Record name    "SCALEn"       n=1, 2, or 3
  # 11 - 20       Real(10.6)     s[n][1]        Sn1
  # 21 - 30       Real(10.6)     s[n][2]        Sn2
  # 31 - 40       Real(10.6)     s[n][3]        Sn3
  # 46 - 55       Real(10.5)     u[n]           Un
  assert [unit_cell, fractionalization_matrix].count(None) == 1
  if (unit_cell is not None):
    f = unit_cell.fractionalization_matrix()
  else:
    assert len(fractionalization_matrix) == 9
    f = fractionalization_matrix
  assert len(u) == 3
  return (("SCALE1    %10.6f%10.6f%10.6f     %10.5f\n"
           "SCALE2    %10.6f%10.6f%10.6f     %10.5f\n"
           "SCALE3    %10.6f%10.6f%10.6f     %10.5f") % (
    f[0], f[1], f[2], u[0],
    f[3], f[4], f[5], u[1],
    f[6], f[7], f[8], u[2])).replace(" -0.000000", "  0.000000")

def format_cryst1_and_scale_records(
      crystal_symmetry=None,
      cryst1_z=None,
      write_scale_records=True,
      scale_fractionalization_matrix=None,
      scale_u=[0,0,0]):
  from cctbx import crystal
  from cctbx import sgtbx
  from cctbx import uctbx
  from scitbx import matrix
  if (crystal_symmetry is None):
    unit_cell = None
    space_group_info = None
  elif (isinstance(crystal_symmetry, crystal.symmetry)):
    unit_cell = crystal_symmetry.unit_cell()
    space_group_info = crystal_symmetry.space_group_info()
  elif (isinstance(crystal_symmetry, uctbx.ext.unit_cell)):
    unit_cell = crystal_symmetry
    space_group_info = None
  elif (isinstance(crystal_symmetry, (list, tuple))):
    assert len(crystal_symmetry) == 6 # unit cell parameters
    unit_cell = uctbx.unit_cell(crystal_symmetry)
    space_group_info = None
  else:
    raise ValueError("invalid crystal_symmetry object")
  if (unit_cell is None):
    if (scale_fractionalization_matrix is None):
      unit_cell = uctbx.unit_cell((1,1,1,90,90,90))
    else:
      unit_cell = uctbx.unit_cell(
        orthogonalization_matrix=matrix.sqr(
          scale_fractionalization_matrix).inverse())
  if (space_group_info is None):
    space_group_info = sgtbx.space_group_info(symbol="P 1")
  result = format_cryst1_record(
    crystal_symmetry=crystal.symmetry(
      unit_cell=unit_cell, space_group_info=space_group_info),
    z=cryst1_z)
  if (write_scale_records):
    if (scale_fractionalization_matrix is None):
      scale_fractionalization_matrix = unit_cell.fractionalization_matrix()
    result += "\n" + format_scale_records(
      fractionalization_matrix=scale_fractionalization_matrix,
      u=scale_u)
  return result

class read_scale_record:

  def __init__(self, line, source_info=""):
    try: self.n = int(line[5:6])
    except ValueError: self.n = None
    if (self.n not in [1,2,3]):
      raise RuntimeError(
        "Unknown PDB record %s%s" % (show_string(line[:6]), source_info))
    values = []
    for i in [10,20,30,45]:
      fld = line[i:i+10]
      if (len(fld.strip()) == 0):
        value = 0
      else:
        try: value = float(fld)
        except ValueError:
          raise RuntimeError(
            "Not a floating-point value, PDB record %s%s:\n" % (
              show_string(line[:6]), source_info)
            + "  " + line + "\n"
            + "  %s%s" % (" "*i, "^"*10))
      values.append(value)
    self.sn1, self.sn2, self.sn3, self.un = values

def resseq_decode(s):
  return hy36decode(width=4, s="%4s" % s)

def resseq_encode(value):
  return hy36encode(width=4, value=value)

def encode_serial_number(width, value):
  if (isinstance(value, str)):
    assert len(value) <= width
    return value
  if (isinstance(value, int)):
    return hy36encode(width=width, value=value)
  raise RuntimeError("serial number value must be str or int.")

def format_atom_record(record_name="ATOM",
                       serial=0,
                       name=" C  ",
                       altLoc=" ",
                       resName="DUM",
                       chainID=" ",
                       resSeq=1,
                       iCode=" ",
                       site=(0,0,0),
                       occupancy=1,
                       tempFactor=0,
                       segID="    ",
                       element="  ",
                       charge="  "):
  # ATOM
  #  7 - 11  Integer       serial        Atom serial number.
  # 13 - 16  Atom          name          Atom name.
  # 17       Character     altLoc        Alternate location indicator.
  # 18 - 20  Residue name  resName       Residue name.
  # 21 - 22                chainID       Chain identifier.
  # 23 - 26  Integer       resSeq        Residue sequence number.
  # 27       AChar         iCode         Code for insertion of residues.
  # 31 - 38  Real(8.3)     x             Orthogonal coordinates for X in
  #                                      Angstroms.
  # 39 - 46  Real(8.3)     y             Orthogonal coordinates for Y in
  #                                      Angstroms.
  # 47 - 54  Real(8.3)     z             Orthogonal coordinates for Z in
  #                                      Angstroms.
  # 55 - 60  Real(6.2)     occupancy     Occupancy.
  # 61 - 66  Real(6.2)     tempFactor    Temperature factor.
  # 73 - 76  LString(4)    segID         Segment identifier, left-justified.
  # 77 - 78  LString(2)    element       Element symbol, right-justified.
  # 79 - 80  LString(2)    charge        Charge on the atom.
  return ((
    "%-6.6s%5.5s %-4.4s%1.1s%-3.3s%2.2s%4.4s%1.1s"
    "   %8.3f%8.3f%8.3f%6.2f%6.2f    "
    "  %-4.4s%2.2s%2.2s") % (
      record_name,
      encode_serial_number(width=5, value=serial),
      name, altLoc, resName, chainID,
      encode_serial_number(width=4, value=resSeq), iCode,
      site[0], site[1], site[2], occupancy, tempFactor,
      segID, element, charge)).rstrip()

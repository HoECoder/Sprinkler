import os
import os.path
import glob
import json
from copy import deepcopy
from collections import OrderedDict
from core_config import *
from settings_keys import *
from programs import *
from singleton import *
from utility import find_key_gap
from clock import pretty_now
from program_log import sqlite_program_log

class ProgramManager(object):
    def __init__(self, programs_path = programs_path, logger = sqlite_program_log):
        self.logger = logger
        self.programs_path = programs_path
        exists = os.path.exists(self.programs_path)
        if not exists:
            os.makedirs(self.programs_path)
        self.__programs = OrderedDict()
        self.__program_paths = OrderedDict()
        self.__running_program = None
        self.__even_keys = set()
        self.__odd_keys = set()
        self.__dow_keys = set()
        self.__key_set_helper = {EVEN_INTERVAL_TYPE : self.__even_keys ,
                                 ODD_INTERVAL_TYPE : self.__odd_keys ,
                                 DOW_INTERVAL_TYPE : self.__dow_keys}
        self.program_glob = os.path.join(self.programs_path, program_name_glob)
    
    # Dictionary interface
    def __getitem__(self, key):
        return self.__programs[key]
    def __setitem__(self, program_id, new_program):
        program = self.__programs.get(program_id, None)
        if program is None:
            self.add_program(new_program)
        else:
            self.__programs[program_id] = new_program
            new_program.dirty = True
    def has_key(self, key):
        return self.__programs.has_key(key)
    def keys(self):
        return self.__programs.keys()
    def values(self):
        return self.__programs.values()
    def items(self):
        return self.__programs.items()
    def __len__(self):
        return len(self.__programs)
    
    def change_program_path(self, path):
        
        if path != self.programs_path:
            self.programs_path = path
            if not os.path.exists(self.programs_path):
                os.makedirs(self.programs_path)
            self.program_glob = os.path.join(self.programs_path, program_name_glob)
    
    @property
    def dirty(self):
        return reduce(lambda a, b: a or b.dirty, self.__programs.values(), False)
    def add_program(self, program, write_through = False):
        program_key_set = self.__programs.keys()
        program_id = find_key_gap(program_key_set)
        program.program_id = program_id
        self.__programs[program_id] = program
        program.dirty = True
        if write_through:
            self.write_program(program)
        return program_id
    def delete_program(self, program_id):
        program = self.__programs.pop(program_id, None)
        program.dirty = False
        full_path = os.path.join(self.programs_path, program_name_template % program.program_id)
        os.remove(full_path)
        program.program_id = 0
        return program
    def write_program(self, program):
        file_name = os.path.join(self.programs_path, program_name_template % program.program_id)
        program_file = open(file_name,"wb")
        s = program.serialize()
        json.dump(s, program_file, indent = 4)
        program_file.flush()
        program_file.close()
        del program_file
        program.dirty = False
    def write_programs(self):
        for pid, program in self.__programs.items():
            if program.dirty: # Effeciency, less disk access
                # Force the program to serialize, then turn the resultant into a JSON string
                # This makes a nice, user friendly format
                self.write_program(program)
    def load_programs(self):
        program_paths = glob.glob(self.program_glob)
        programs = OrderedDict()
        loaded = 0
        key_set_helper = {EVEN_INTERVAL_TYPE: self.__even_keys,
                          ODD_INTERVAL_TYPE : self.__odd_keys,
                          DOW_INTERVAL_TYPE : self.__dow_keys}
        for pp in program_paths:
            old_file_time = self.__program_paths.get(pp, -1.0)
            new_file_time = os.stat(pp).st_mtime
            if old_file_time < new_file_time:
                try:
                    program_file = open(pp,"rb")
                    program_d = json.load(program_file)
                    program = unpack_program(program_d, self, self.logger)
                    programs[program.program_id] = program
                    program_file.close()
                    del program_file
                    loaded += 1
                    key_set = self.__key_set_helper[program.interval]
                    key_set.add(program.program_id)
                    self.__program_paths[pp] = new_file_time
                except IOError, e:
                    print str(e)
        if len(programs) > 0: # TODO : Need to evaluate programs for overlap. The scheduling problem
            self.__programs = programs
            return loaded
        else:
            return loaded
    # Here we bind the controller's stations to the StationBlocks in the programs
    def bind_stations(self, controller_stations):
        for program in self.__programs.values():
            for station in controller_stations.values():
                sb = program.get(station.station_id, None)
                if not sb is None:
                    sb.bound_station = station
            program.fix_start_end()
        
    def running_programs(self):
        return set(self.__running_program)
        #return filter(lambda prog: prog.running, self.__programs.values())
    def move_program(self, program, running):
        if running:
            self.__running_program = program
            self.logger.log_program_start(program)
        else:
            self.__running_program = None
            self.logger.log_program_stop(program)
    def non_running_programs(self):
        return filter(lambda prog: not prog.running, self.__programs.values())
    
    def get_program_to_run(self, now): # We short circuit out of this one the second we find a program
        if not self.__running_program is None:
            return self.__running_program
        if now[TIME_DAY_KEY] % 2 == 0:
            even_odd = EVEN_INTERVAL_TYPE
        else:
            even_odd = ODD_INTERVAL_TYPE
        dow = now[TIME_DOW_KEY]
        even_odd_key_set = self.__key_set_helper[even_odd]
        
        for program_id in even_odd_key_set:
            program = self.__programs[program_id]
            if START == program.evaluate(now):
                program.running = True
                return program
        for program_id in self.__dow_keys:
            program = self.__programs[key]
            if dow in program.dow:
                if START == program.evaluate(now):
                    program.running = True
                    return program
        return None

program_manager = ProgramManager()

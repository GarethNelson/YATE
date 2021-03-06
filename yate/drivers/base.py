import os
import sys
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir))

import yatelog
from yateproto import *

import time

class YateBaseVoxel:
   """ This class may either be used directly or inherited from and extended for game-specific mechanics etc
   """
   def __init__(self,spatial_pos=(64,64,64),basic_type=YATE_VOXEL_EMPTY,specific_type=0,active_state=YATE_VOXEL_INACTIVE,intact_state=YATE_VOXEL_INTACT,from_params=None):
       """ spatial_pos   is obvious
           basic_type    is the basic voxel type as defined in yateproto.py
           specific_type is optional and specifies the game-specific extended type
           active_state and intact_state only make sense in certain contexts:
               doors are active when open, other stuff may be active or not if it makes sense
               partly destroyed voxels are not intact
           from_params   is a tuple of params from a MSGTYPE_VOXEL_UPDATE message and defaults to None
                         if specified, from_params overrides other params
       """
       if from_params is None:
          self.spatial_pos   = (spatial_pos[0],spatial_pos[1],spatial_pos[2])
          self.basic_type    = basic_type
          self.specific_type = specific_type
          self.active_state  = active_state
          self.intact_state  = intact_state
       else:
          self.spatial_pos   = from_params[0]
          self.basic_type    = from_params[1]
          self.specific_type = from_params[2]
          self.active_state  = from_params[3]
          self.intact_state  = from_params[4]

   def __str__(self):
       return 'VOXEL@%s: basic_type:%s,specific_type:%s' % (str(self.spatial_pos),self.basic_type,self.specific_type)

   def get_basic_type(self):
       """ return the basic type of the voxel as an integer
       """
       return self.basic_type       
   def get_specific_type(self):
       """ Return the specific type of the voxel as an integer
       """
       self.specific_type
   def get_pos(self):
       """ return a tuple representing the 3D spatial coordinates of this voxel
       """
       return self.spatial_pos
   def as_msgparams(self):
       """ return a tuple representing this voxel as message params for MSGTYPE_VOXEL_UPDATE
       """
       return ((self.spatial_pos[0],self.spatial_pos[1],self.spatial_pos[2]),self.basic_type,self.specific_type,self.active_state,self.intact_state)
   def is_intact(self):
       """" return a boolean value indicating whether or not this voxel is fully intact
            if it's partly destroyed, this will return false
       """
       if self.intact_state==YATE_VOXEL_INTACT: return True
       return False
   def is_active(self):
       """ return a boolean value indicating whether or not this voxel is active, whatever that means in context
       """
       if self.intact_state == YATE_VOXEL_ACTIVE: return True
       return False
   def is_open(self):
       """ return a boolean value indicating whether or not this voxel is open - this makes no sense unless it's a door
           none-door voxels can thus never be opened
       """
       return self.can_open() and self.is_active()
   def can_open(self):
       """ return a boolean value indicating whether or not this voxel can be opened, i.e is it a door
           this method could be overridden to implement keys and such
       """
       return {YATE_VOXEL_EMPTY:             False,
               YATE_VOXEL_TOTAL_OBSTACLE:    False,
               YATE_VOXEL_EASY_OBSTACLE:     False,
               YATE_VOXEL_DOOR_OBSTACLE:     True,
               YATE_VOXEL_DOOR_EASY_DESTROY: self.is_intact(), # we assume doors that are not intact can not be opened
               YATE_VOXEL_DOOR_HARD_DESTROY: self.is_intact(),
               YATE_VOXEL_HARD_OBSTACLE:     False,
               YATE_VOXEL_UNKNOWN:           False}[self.basic_type]       
   def can_traverse(self, no_destroy=False, no_interact=False):
       """ return a boolean value indicating whether or not this voxel can be traversed by YATE automatically during pathfinding
           if no_destroy is set to True, we assume that YATE_VOXEL_EASY_OBSTACLE will not be destroyed
           if no_interact is set to True, we assume that YATE_VOXEL_DOOR_OBSTACLE will not be interacted with
           if the voxel basic type is unknown, we assume it can NOT be traversed until proven otherwise
           this method will also throw an exception if self.basic_type is not a proper basic type
       """
       if self.is_open(): return True # this only makes sense for doors - if we are not a door, isopen should always be False
       return {YATE_VOXEL_EMPTY:             True,
               YATE_VOXEL_TOTAL_OBSTACLE:    False,
               YATE_VOXEL_EASY_OBSTACLE:     not no_destroy,
               YATE_VOXEL_DOOR_OBSTACLE:     not no_interact,
               YATE_VOXEL_DOOR_EASY_DESTROY: (not no_destroy) or (not no_interact),
               YATE_VOXEL_DOOR_HARD_DESTROY: not no_interact,
               YATE_VOXEL_HARD_OBSTACLE:     False,
               YATE_VOXEL_UNKNOWN:           False}[self.basic_type]
   
   def can_destroy(self):
       """ return a boolean value indicating whether or not this voxel can be destroyed by YATE automatically during pathfinding
           if the voxel can only be destroyed with effort, this will return False
       """
       return {YATE_VOXEL_EMPTY:             False,
               YATE_VOXEL_TOTAL_OBSTACLE:    False,
               YATE_VOXEL_EASY_OBSTACLE:     True,
               YATE_VOXEL_DOOR_OBSTACLE:     False, # doors should never be destroyed automatically
               YATE_VOXEL_DOOR_EASY_DESTROY: False,
               YATE_VOXEL_DOOR_HARD_DESTROY: False,
               YATE_VOXEL_HARD_OBSTACLE:     False,
               YATE_VOXEL_UNKNOWN:           False}[self.basic_type]
 
class YateBaseDriver(object):
   """ This class is the base used for all drivers
       At time of writing the only supported game in YATE is minecraft, so that is the only class inheriting from this one
   """
   def __init__(self,username=None,password=None,server=None,verbose=False):
       """ When overriding, the constructor should setup the connection and get into a state where the game is playable
           by the AI's avatar - the username,password and server params are self explanatory and may optionally be ignored
           if doing so is appropriate. If the setup fails, then the constructor should throw an exception
       """
   def get_vision_range(self):
       """ Returns an (x,y,z) tuple representing how many voxels can be perceived by the in-game avatar
           This must always be an even number on each axis, even if that means losing data, also needs to fit into a single bulk update
           z is height
       """
       pass
   def respawn(self):
       """ If the AI's avatar is dead, respawn if possible - if respawning requires a particular amount of time
           this method should block. If the AI's avatar is alive and it is possible to do so, this method should
           force a respawn
       """
       pass
   def tick(self):
       """ This method will be called in a loop by YATE
           If the game requires particular timing for things such as keepalive packets it should be tracked here.
           This method should NOT block using time.sleep or similar, if precise timing is needed then eventlet's sleep can be used to implement it
       """
       pass
   def get_rot(self):
       """ Should return a tuple representing the avatar's rotation in 3 spatial axis, in degrees - these values should be clamped to within 0-360 for obvious reasons
       """
       pass
   def get_pos(self):
       """ This method should return a tuple representing coordinates in 3D space of the AI's avatar
       """
       pass
   def destroy_voxel(self,spatial_pos):
       """ This method attempts to destroy the voxel specified
       """
       pass
   def interact_voxel(self,spatial_pos):
       """ This method attempts to interact with the voxel specified
       """
       pass
   def walk_to_space(self,spatial_pos):
       """ This method should attempt to walk as close as possible to the specified space with an appropriate pathfinding algorithm
           Failed attempts are acceptable as this method is intended as a primitive for higher-level algorithms on the AI side
       """
       pass
   def move_vector(self,vector):
       """ This method is used by the base pathfinding algorithm to move the avatar in a specific direction
           vector is simply a tuple specifying a 3D vector (i.e how much to try and move in each direction)
           As with walk_to_space() failed attempts are both acceptable and expected
           This method should attempt to destroy and interact as appropriate
       """
       pass
   def get_voxel(self,voxel_pos):
       """ This method should return a voxel object describing the specified 3D coordinates. If the AI's avatar can not
           see the coordinates this method should return None
       """
       pass
   def get_voxel_strings(self):
       """ This method should return a dict that maps extended voxel type integers to strings
       """
       pass
   def get_entity_strings(self):
       """ This method should return a dict that maps entity type integers to strings
       """
       pass
   def get_item_strings(self):
       """ This method should return a dict that maps item type integers to strings
       """
       pass

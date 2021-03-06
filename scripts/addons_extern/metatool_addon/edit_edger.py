import bpy
import bmesh
import mathutils
import bgl
from bpy_extras.view3d_utils import location_3d_to_region_2d

#bl_info = {
#    "name": "Edger",
#    "author": "Reslav Hollos",
#    "version": (0, 2, 9),
#    "blender": (2, 72, 0),
#    "description": "Lock vertices on \"edge\" they lay, make unselectable edge loops for subdivision",
#    "warning": "",
#    "wiki_url": "",
#    "category": "Mesh"
#}

#TODO check if passing context instead of bpy.context is neccessery
#TODO bug in ctrlR adding edgeloop adds it to groups, when this is resolved lock groups after assign just to prevent user modifying
#TODO if _edger_group vert is selected, select its closer edge afte deselecting
#TODO when groups are added/deleted ReInit
#TODO reinit on history change
#TODO try alt rmb shortcut to deactivate so verts dont deselect
#TODO moving and canceling with RMB spawns shadows
#TODO detect group from selected and remove via button

def GetGroupVerts(obj, bm):
    groupVerts = {}
    if obj and bm:
        for g in obj.vertex_groups:
            if g.name.startswith("_edger_"):
                groupVerts[g] = []
        
        deform_layer = GetDeformLayer(bm)
        
        deletion = []
        
        for v in bm.verts:
            for g in groupVerts:
                if g.index in v[deform_layer]:
                    #if v not in groupVerts[g]:
                    groupVerts[g].append(v)
        
        for g in groupVerts:
            if len(groupVerts[g]) is 0:
                deletion.append(g)
        
        #delete empty
        groupVerts = {k: v for k, v in groupVerts.items() if len(v) is not 0}
        DeleteGroups(obj, deletion)
            
    return groupVerts

def DeleteGroups(obj, groups):
    for g in groups: DeleteGroup(obj, g)

def DeleteGroup(obj, g):
    obj.vertex_groups.remove(g)    
    
def AddNewVertexGroup(name):
    #TODO make check if selected are already part of _edger_ group
    try: bpy.context.object.vertex_groups[groupName]
    except: return bpy.context.object.vertex_groups.new(name)
    return None

'''
def DeselectGroups(groupVerts):
    for g in groupVerts:
        for v in groupVerts[g]:
            try: v.select = False
            except: ReInit()
'''

#def DeselectGroupsSelectCloser(adjInfos):
def DeselectGroups(adjInfos):
    for i in adjInfos:
        try: 
            if i.target.select is True:            
                i.target.select = False
                if i.ratioToEnd1 < 0.5:
                    i.end1.select = True
                else: i.end2.select = True
        except: ReInit()

def AdjacentVerts(v, exclude = []):    
    adjacent = []
    for e in v.link_edges:
        if e.other_vert(v) not in exclude:
            adjacent.append(e.other_vert(v))
    return adjacent
        
def GetAdjInfos(groupVerts):
    adjInfos = []
    for g in groupVerts:
        for v in groupVerts[g]:
            adj = AdjacentVerts(v, groupVerts[g])
            if len(adj) is 2:
                aifv = AdjInfoForVertex(v, adj[0], adj[1])
                adjInfos.append(aifv)
    return adjInfos

class AdjInfoForVertex(object):
    def __init__(self, target, end1, end2):
        self.target = target
        self.end1 = end1
        self.end2 = end2
        self.UpdateRatio()

    def UpdateRatio(self):
        end1ToTarget = (self.end1.co -self.target.co).length
        end1ToEnd2 = (self.end1.co -self.end2.co).length
        self.ratioToEnd1 = end1ToTarget/end1ToEnd2; #0 is end1, 1 is end2
       
    def LockTargetOnEdge(self):
        # c = a + r(b -a)
        self.target.co = self.end1.co +self.ratioToEnd1*(self.end2.co -self.end1.co)

def LockVertsOnEdge(adjInfos):
    for i in adjInfos:
        i.LockTargetOnEdge()
        
def GetDeformLayer(bm):
    deform_layer = bm.verts.layers.deform.active
    if deform_layer is None: 
        return bm.verts.layers.deform.new()
    return deform_layer
     
def RemoveVertsFromGroup(bm, verts, g):
    if g is None: return 
    deform_layer = GetDeformLayer(bm)
    for v in verts:
        del v[deform_layer][g.index]

def AddSelectedToGroup(bm, g):
    deform_layer = GetDeformLayer(bm)
    for v in bm.verts:
        if v.select is True:
            v[deform_layer][g.index] = 1     #set weight to 1 as usual default

def GetGroupByName(name):
    try: return bpy.context.object.vertex_groups[name]
    except: return None

def draw_callback_px(self, context):
    if context.scene.isEdgerDebugActive is False:
        return
    
    obj = context.object
    context.area.tag_redraw()
    
    #draw unselectables
    #verts2d = from group _unselectable_
    #DrawByVertices("points", verts2d, [0.5, 1.0, 0.1, 0.5])
    
    for g in groupVerts:
        verts2d = []
        for v in groupVerts[g]:
            try:
                v_worldCo = obj.matrix_world*v.co
                #v_worldCo = v.co
                new2dCo = location_3d_to_region_2d(context.region, context.space_data.region_3d, v_worldCo)
                verts2d.append([new2dCo.x,new2dCo.y])
            except:
                #TODO this happens when running as script and not as addon since multiple registered instances exist, qfix:restart blender 
                continue
        DrawByVertices("lines", verts2d, [0.5, 0.1, 0.1, 0.5])

def SortGroupVertsByAdjacent(groupVerts):
    for g in groupVerts:
        ordered = []
        #GetGroupVerts removes empty so len(groupVerts[g]) always >0
        ordered.append(groupVerts[g].pop(0))
        while len(groupVerts[g]) > 0:
            a = NextAdjacentInLoop(ordered[len(ordered)-1], groupVerts[g])
            if a is not None:
                ordered.append(a)
                groupVerts[g].remove(a)
                continue
            #TODO that means loop group isn't a loop and contains disconnected verts, debug this to user!
            break
        if len(groupVerts[g]) is 0:
            groupVerts[g] = ordered            
        else:
            #TODO debug to user, maybe remove verts from group so it gets deleted from GetGroupVerts (?)
            groupVerts[g] = ordered + groupVerts[g]
        
def NextAdjacentInLoop(v, loopVerts):
    for e in v.link_edges:
        if e.other_vert(v) in loopVerts:
            return e.other_vert(v)
    return None

def DrawByVertices(mode, verts2d, color):
    bgl.glColor4f(*color)
    
    bgl.glEnable(bgl.GL_BLEND)
    
    if mode is "points":
        bgl.glPointSize(5)
        bgl.glBegin(bgl.GL_POINTS)
            
    elif mode is "lines":
        bgl.glLineWidth(2)
        bgl.glBegin(bgl.GL_LINE_LOOP)
    
    for x, y in verts2d:
        bgl.glVertex2f(x, y)

    bgl.glEnd()
    bgl.glDisable(bgl.GL_BLEND)
    #restore defaults
    bgl.glLineWidth(1)
    bgl.glColor4f(0.0, 0.0, 0.0, 1.0)

    return

#INIT
def ReInit(context = None):
    global obj, me, bm
    global groupVerts, adjInfos
    obj = bpy.context.object
    if context is not None:
        obj = context.object
    me = obj.data
    bm = bmesh.from_edit_mesh(me)
    
    #compare groupVerts vertices by index and position, if there are external remove them from group
    groupVerts = GetGroupVerts(obj, bm)
    SortGroupVertsByAdjacent(groupVerts)
    adjInfos = GetAdjInfos(groupVerts)
    #RemoveVertsFromGroup(bm, bm.verts, GetGroupByName("_edger_.0"))

#has to be global to sustain adjInfos between modal calls :'( sorry global haters )':
isEditMode = False
obj, me, bm = None, None, None
groupVerts = {}     #dict[g] = [list, of, vertices]
adjInfos = []
        
bpy.types.Scene.isEdgerActive = bpy.props.BoolProperty(
    name="Active", description="Toggle if Edger is active", default=False)
bpy.types.Scene.isEdgerDebugActive = bpy.props.BoolProperty(
    name="Draw", description="Toggle if edge loops and unselectables should be drawn", default=False)

class LockEdgeLoop(bpy.types.Operator):
    """Lock this edge loop as if it was on flat surface"""
    bl_idname = "wm.lock_edge_loop_idname"
    bl_label = "LockEdgeLoop_label"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'
    
    def execute(self, context):
        obj = context.object
        me = obj.data
        bm = bmesh.from_edit_mesh(me)
        
        name = "_edger_"
        counter = 0
        
        while GetGroupByName(name + "." + str(counter)) is not None:
            counter += 1
        g = AddNewVertexGroup(name + "." + str(counter))
        AddSelectedToGroup(bm, g)
        
        #fetch new group
        #newVerts = []
        #deform_layer = GetDeformLayer(bm)
        #for v in bm.verts:
        #    if g.index in v[deform_layer]:
        #        newVerts.append(v)
        
        #RemoveVertsIfSubsetOfOtherGroups(newVerts, bm, groupVerts)
        ReInit()
        
        return {'FINISHED'}

#remove all verts of of_g from all other groups if of_g is their subset 
def RemoveVertsIfSubsetOfOtherGroups(verts, bm, groupVerts):
    for g in groupVerts:
        if DoesListContainsList(groupVerts[g], verts):
            RemoveVertsFromGroup(bm, verts, g)

def DoesListContainsList(big, small):
    for s in small:
        if s not in big: return False
    return True

class UnselectableVertices(bpy.types.Operator):
    """Make selected vertices unselectable"""
    bl_idname = "wm.unselectable_vertices_idname"
    bl_label = "unselectable_vertices_label"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'
    
    def execute(self, context):
        global obj, me, bm
        name = "_unselectable_"
        g = GetGroupByName(name)
        if g is not None:
            g = AddNewVertexGroup(name)
        AddSelectedToGroup(bm, g)

        return {'FINISHED'}

'''
def DeselectAll(bm):
    for f in bm.faces:
        f.select = False
'''
def MakeSelectedOnlyVertsInGroup(bm, g):
    deform_layer = GetDeformLayer(bm)
    for f in bm.faces:
        f.select = False
        for v in f.verts:
            if g.index in v[deform_layer]:
                v.select = True

def DuplicateObject():
    bpy.ops.object.mode_set(mode = 'OBJECT') 
    bpy.ops.object.duplicate_move()
    bpy.ops.object.mode_set(mode = 'EDIT') 
    
class ClearEdgerLoops(bpy.types.Operator):
    """Create duplicate of object and remove _edger_ vertexGroups and delete their Edge Loops"""
    bl_idname = "wm.clear_edger_oops_idname"
    bl_label = "clear_edger_oops__label"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'
    
    def execute(self, context):
        DuplicateObject()
        ReInit()
        global obj, me, bm
        global groupVerts
        
        context.scene.isEdgerActive = False

        groups = []
        for g in obj.vertex_groups:
            if g.name.startswith("_edger_"):
                groups.append(g)
        for g in groups:
            MakeSelectedOnlyVertsInGroup(bm, g)
            bpy.ops.object.mode_set(mode = 'OBJECT') 
            bpy.ops.object.mode_set(mode = 'EDIT') 
            bpy.ops.mesh.delete_edgeloop()
            ReInit(context)                    
        
        #once empty groups will be automatically deleted
        return {'FINISHED'}
    
'''
class EdgerFunc1(bpy.types.Operator):
    """EdgerFunc1"""
    bl_idname = "wm.edger_func1_idname"
    bl_label = "EdgerFunc1_label"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'
    
    def execute(self, context):
      
        return {'FINISHED'}
'''
class Edger(bpy.types.Operator):
    """Lock vertices on edge"""
    bl_idname = "wm.edger"
    bl_label = "Edger"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'
    
    _timer = None
    
    def modal(self, context, event):
        #if event.type == 'ESC':
        #    return self.cancel(context)
        
        if event.type == 'TIMER':
            if context.object is None:
                return {'PASS_THROUGH'}
            
            if context.object.mode == "EDIT":
                global isEditMode
                obj = context.object
                me = obj.data
                bm = bmesh.from_edit_mesh(me)
                global groupVerts, adjInfos
                
                if isEditMode is False:
                    isEditMode = True
                    ReInit()
                
                me.update()
                    
                if context.scene.isEdgerActive is False:
                    return {'PASS_THROUGH'}
                    
                DeselectGroups(adjInfos)
                LockVertsOnEdge(adjInfos)
                                
                # change theme color, silly!
                #color = context.user_preferences.themes[0].view_3d.space.gradients.high_gradient
                #color.s = 1.0
                #color.h += 0.01
            else:
                isEditMode = False

        return {'PASS_THROUGH'}

    def execute(self, context):
        self._timer = context.window_manager.event_timer_add(0.03, context.window)
        
        args = (self, context)
        self._handle = bpy.types.SpaceView3D.draw_handler_add(draw_callback_px, args, 'WINDOW', 'POST_PIXEL')

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        context.window_manager.event_timer_remove(self._timer)
        bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
        return {'CANCELLED'}

#addon_keymaps = []
#def menu_func_edger(self, context): self.layout.operator(Edger.bl_idname
"""
class EdgerPanel(bpy.types.Panel):
    bl_label = "Edger"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'   #TODO
    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.prop(context.scene, 'isEdgerActive')
        row.prop(context.scene, 'isEdgerDebugActive')
        split = layout.split()
        col = split.column(align=True)
        #col.operator(UnselectableVertices.bl_idname, text="Unselectable", icon = "RESTRICT_SELECT_ON")
        col.operator(LockEdgeLoop.bl_idname, text="Lock Edge Loop", icon = "GROUP_VERTEX")
        col.operator(ClearEdgerLoops.bl_idname, text="Clear Loops", icon = "MOD_SOLIDIFY")
        row = layout.row()
        #row.label(text="bla bla bla:")
"""
        
#handle the keymap
#wm = bpy.context.window_manager
#km = wm.keyconfigs.addon.keymaps.new(name='UV Editor', space_type='EMPTY')
#kmi = km.keymap_items.new(UvSquaresByShape.bl_idname, 'E', 'PRESS', alt=True)
#addon_keymaps.append((km, kmi))

def init_handler(scene):
    try: bpy.app.handlers.scene_update_pre.remove(init_handler)
    except: return
    bpy.ops.wm.edger()

def register():
    bpy.utils.register_class(Edger)
    #bpy.utils.register_class(EdgerFunc1)
    bpy.utils.register_class(LockEdgeLoop)
    bpy.utils.register_class(ClearEdgerLoops)
    bpy.utils.register_class(UnselectableVertices)
    #bpy.utils.register_class(EdgerPanel)

    bpy.app.handlers.scene_update_pre.append(init_handler)

def unregister():
    bpy.utils.unregister_class(Edger)
    #bpy.utils.unregister_class(EdgerFunc1)
    bpy.utils.unregister_class(LockEdgeLoop)
    bpy.utils.unregister_class(ClearEdgerLoops)
    bpy.utils.unregister_class(UnselectableVertices)
    #bpy.utils.unregister_class(EdgerPanel)

if __name__ == "__main__":
    register()

    # start edger
    bpy.ops.wm.edger()
bl_info = {
    "name": "GS Model Helper",
    "author": "DaKashi",
    "version": (2, 2),  # Bumped version
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > GS Model Helper",
    "description": "Small collection of useful tools for Goldsource models",
    "category": "Object",
}

import bpy
import itertools
import bmesh
import os
import re
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------
# UTILITY FUNCTIONS
# ------------------------------------------------------------

def ensure_edit_mode(obj):
    """Context manager to ensure object is in edit mode and restore original mode"""
    class EditModeManager:
        def __init__(self, obj):
            self.obj = obj
            self.original_mode = obj.mode if obj else None
            
        def __enter__(self):
            if self.obj and self.obj.mode != 'EDIT':
                bpy.ops.object.mode_set(mode='EDIT')
            return self
            
        def __exit__(self, exc_type, exc_val, exc_tb):
            if self.obj and self.original_mode and self.original_mode != 'EDIT':
                bpy.ops.object.mode_set(mode=self.original_mode)
    
    return EditModeManager(obj)

def validate_active_object(context, required_type='MESH', require_selected=False):
    """Enhanced validation with more options and better error messages"""
    if require_selected and not context.selected_objects:
        return None, "No objects selected"
    
    obj = context.active_object
    if not obj:
        return None, "No active object selected"
    if obj.type != required_type:
        return None, f"Active object must be a {required_type.lower()}, not {obj.type.lower()}"
    return obj, None

def clean_name_to_bmp(name: str) -> str:
    """Remove extensions and numeric suffixes, ensure .bmp at end"""
    if not name.strip():
        return "unnamed.bmp"
    base = re.sub(r"\.\d+$", "", name)  # remove numeric .001 etc
    base = os.path.splitext(base)[0]   # remove extension
    return base + ".bmp"

def validate_operation_possible(context, operator_type):
    """Check if operation can be performed with specific validation"""
    if operator_type == 'vertex_groups':
        obj = context.active_object
        return obj and obj.type == 'MESH' and obj.vertex_groups
    elif operator_type == 'armature':
        obj = context.active_object
        return obj and obj.type == 'ARMATURE' and obj.data.bones
    return False

# ------------------------------------------------------------
# L/R SWAP OPERATOR (Vertex Groups)
# ------------------------------------------------------------
class OBJECT_OT_swap_rl_vertex_groups(bpy.types.Operator):
    bl_idname = "object.swap_rl_vertex_groups"
    bl_label = "Swap L/R Vertex Groups"
    bl_description = "Swap between the (Left) or (Right) prefix. Useful for viewmodels"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj, error = validate_active_object(context, 'MESH')
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}

        if not obj.vertex_groups:
            self.report({'WARNING'}, "No vertex groups found on this mesh")
            return {'CANCELLED'}

        swapped_count = 0
        for vg in obj.vertex_groups:
            original_name = vg.name
            if " R " in vg.name:
                vg.name = vg.name.replace(" R ", " L ")
                swapped_count += 1
            elif " L " in vg.name:
                vg.name = vg.name.replace(" L ", " R ")
                swapped_count += 1

        if swapped_count == 0:
            self.report({'INFO'}, "No L/R vertex groups found to swap")
        else:
            self.report({'INFO'}, f"Swapped {swapped_count} vertex groups")
        return {'FINISHED'}


# ------------------------------------------------------------
# VALVE ↔ GEARBOX LIMB SWAP
# ------------------------------------------------------------
limb_suffix_map = {
    "L Leg": "L Thigh",
    "L Leg1": "L Calf",
    "R Leg": "R Thigh",
    "R Leg1": "R Calf",
    "L Arm": "L Clavicle",
    "L Arm1": "L UpperArm",
    "L Arm2": "L Forearm",
    "R Arm": "R Clavicle",
    "R Arm1": "R UpperArm",
    "R Arm2": "R Forearm",
}
reverse_suffix_map = {v: k for k, v in limb_suffix_map.items()}

def _swap_by_suffix(name: str) -> str:
    for suf, mapped in limb_suffix_map.items():
        needle = " " + suf
        if name.endswith(needle):
            prefix = name[: -len(needle)]
            return f"{prefix} {mapped}"
    for suf, mapped in reverse_suffix_map.items():
        needle = " " + suf
        if name.endswith(needle):
            prefix = name[: -len(needle)]
            return f"{prefix} {mapped}"
    return name


# ------------------------------------------------------------
# PREFIX RENAMER
# ------------------------------------------------------------
class OBJECT_OT_rename_prefix(bpy.types.Operator):
    bl_idname = "object.rename_prefix"
    bl_label = "Rename Prefix"
    bl_description = "Rename prefix of vertex groups or skeleton depending on selection"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        props = scene.gsmodelhelper_props
        obj = context.active_object
        
        if not obj:
            self.report({'ERROR'}, "No active object selected")
            return {'CANCELLED'}

        renamed_count = 0
        
        if obj.type == 'MESH':
            from_text = props.vertex_from.strip()
            to_text = props.vertex_to.strip()
            
            if not from_text:
                self.report({'WARNING'}, "'From' field cannot be empty")
                return {'CANCELLED'}
            
            if not obj.vertex_groups:
                self.report({'WARNING'}, "No vertex groups found on this mesh")
                return {'CANCELLED'}
                
            for vg in obj.vertex_groups:
                if from_text in vg.name:
                    vg.name = vg.name.replace(from_text, to_text)
                    renamed_count += 1
                    
        elif obj.type == 'ARMATURE':
            from_text = props.skel_from.strip()
            to_text = props.skel_to.strip()
            
            if not from_text:
                self.report({'WARNING'}, "'From' field cannot be empty")
                return {'CANCELLED'}
            
            if not obj.data.bones:
                self.report({'WARNING'}, "No bones found in this armature")
                return {'CANCELLED'}
                
            for bone in obj.data.bones:
                if from_text in bone.name:
                    bone.name = bone.name.replace(from_text, to_text)
                    renamed_count += 1
        else:
            self.report({'ERROR'}, "Active object must be a mesh or armature")
            return {'CANCELLED'}

        if renamed_count == 0:
            self.report({'INFO'}, f"No items found containing '{from_text}'")
        else:
            self.report({'INFO'}, f"Renamed {renamed_count} items")
        return {'FINISHED'}


# ------------------------------------------------------------
# COMBINED LIMB SWAP
# ------------------------------------------------------------
class OBJECT_OT_swap_limbs(bpy.types.Operator):
    bl_idname = "object.swap_limbs"
    bl_label = "Swap Limbs"
    bl_description = "Swap Valve & Gearbox limb names for vertex groups or skeleton depending on selection"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj:
            self.report({'ERROR'}, "No active object selected")
            return {'CANCELLED'}

        swapped_count = 0
        
        if obj.type == 'MESH':
            if not obj.vertex_groups:
                self.report({'WARNING'}, "No vertex groups found on this mesh")
                return {'CANCELLED'}
                
            for vg in obj.vertex_groups:
                new_name = _swap_by_suffix(vg.name)
                if new_name != vg.name:
                    vg.name = new_name
                    swapped_count += 1
        elif obj.type == 'ARMATURE':
            if not obj.data.bones:
                self.report({'WARNING'}, "No bones found in this armature")
                return {'CANCELLED'}
                
            for bone in obj.data.bones:
                new_name = _swap_by_suffix(bone.name)
                if new_name != bone.name:
                    bone.name = new_name
                    swapped_count += 1
        else:
            self.report({'ERROR'}, "Active object must be a mesh or armature")
            return {'CANCELLED'}

        if swapped_count == 0:
            self.report({'INFO'}, "No Valve/Gearbox limb names found to swap")
        else:
            self.report({'INFO'}, f"Swapped {swapped_count} limb names")
        return {'FINISHED'}


# ------------------------------------------------------------
# SWAP INPUT FIELDS
# ------------------------------------------------------------
class OBJECT_OT_swap_inputs(bpy.types.Operator):
    bl_idname = "object.swap_inputs"
    bl_label = "Swap Inputs"
    bl_description = "Swap the 'From' and 'To' text fields"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        props = scene.gsmodelhelper_props
        props.vertex_from, props.vertex_to = props.vertex_to, props.vertex_from
        props.skel_from, props.skel_to = props.skel_to, props.skel_from
        self.report({'INFO'}, "Swapped input fields")
        return {'FINISHED'}


# ------------------------------------------------------------
# TEXTURE INTERPOLATION
# ------------------------------------------------------------
class OBJECT_OT_set_interp_closest(bpy.types.Operator):
    bl_idname = "object.set_interp_closest"
    bl_label = "Closest"
    bl_description = "Make textures pixelated (only on selected objects)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not context.selected_objects:
            self.report({'WARNING'}, "No objects selected")
            return {'CANCELLED'}

        processed_count = 0
        for obj in context.selected_objects:
            if obj.type == "MESH" and obj.data.materials:
                for mat in obj.data.materials:
                    if mat and mat.node_tree:
                        for node in mat.node_tree.nodes:
                            if node.type == "TEX_IMAGE":
                                node.interpolation = 'Closest'
                                processed_count += 1
        
        context.scene.gsmodelhelper_props.interp_mode = "CLOSEST"
        
        if processed_count == 0:
            self.report({'WARNING'}, "No texture image nodes found in selected objects")
        else:
            self.report({'INFO'}, f"Set {processed_count} textures to Closest interpolation")
        return {'FINISHED'}


class OBJECT_OT_set_interp_linear(bpy.types.Operator):
    bl_idname = "object.set_interp_linear"
    bl_label = "Linear"
    bl_description = "Make textures filtered (only on selected objects)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not context.selected_objects:
            self.report({'WARNING'}, "No objects selected")
            return {'CANCELLED'}

        processed_count = 0
        for obj in context.selected_objects:
            if obj.type == "MESH" and obj.data.materials:
                for mat in obj.data.materials:
                    if mat and mat.node_tree:
                        for node in mat.node_tree.nodes:
                            if node.type == "TEX_IMAGE":
                                node.interpolation = 'Linear'
                                processed_count += 1
        
        context.scene.gsmodelhelper_props.interp_mode = "LINEAR"
        
        if processed_count == 0:
            self.report({'WARNING'}, "No texture image nodes found in selected objects")
        else:
            self.report({'INFO'}, f"Set {processed_count} textures to Linear interpolation")
        return {'FINISHED'}


# ------------------------------------------------------------
# PROPERTIES
# ------------------------------------------------------------
class GSModelHelper(bpy.types.PropertyGroup):
    vertex_from: bpy.props.StringProperty(
        name="From",
        default="Bip01",
        description="Text to replace in vertex group names",
        update=lambda self, context: self._validate_input(self.vertex_from, "Vertex From")
    )
    vertex_to: bpy.props.StringProperty(
        name="To",
        default="Hands biped",
        description="Replacement text for vertex group names"
    )
    skel_from: bpy.props.StringProperty(
        name="From",
        default="Bip01",
        description="Text to replace in bone names",
        update=lambda self, context: self._validate_input(self.skel_from, "Skeleton From")
    )
    skel_to: bpy.props.StringProperty(
        name="To",
        default="Hands biped",
        description="Replacement text for bone names"
    )
    interp_mode: bpy.props.EnumProperty(
        name="Interpolation Mode",
        items=[("CLOSEST", "Closest", "Pixelated texture filtering"), 
               ("LINEAR", "Linear", "Smooth texture filtering")],
        default="LINEAR",
    )
    
    def _validate_input(self, value, field_name):
        """Validate input and show warning if empty"""
        if not value.strip():
            self.report({'WARNING'}, f"{field_name} cannot be empty")


# ------------------------------------------------------------
# VERTEX OVERLAP CHECKER (optimized)
# ------------------------------------------------------------
class VertexOverlapItem(bpy.types.PropertyGroup):
    groups: bpy.props.StringProperty()
    count: bpy.props.IntProperty()
    verts: bpy.props.StringProperty()
    selected: bpy.props.BoolProperty(default=False)


class OBJECT_OT_check_vertex_overlaps(bpy.types.Operator):
    bl_idname = "object.check_vertex_overlaps"
    bl_label = "Analyze Vertices"
    bl_description = "Summarize overlapping vertex weights by group-pairs"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj, error = validate_active_object(context, 'MESH')
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}

        if not obj.vertex_groups:
            self.report({'WARNING'}, "No vertex groups found on this mesh")
            return {'CANCELLED'}

        scene = context.scene
        scene.vertex_overlap_list.clear()
        
        # Show progress
        wm = context.window_manager
        wm.progress_begin(0, 100)
        
        try:
            # Optimized single-pass overlap detection
            overlaps_map = {}
            vertex_groups = obj.vertex_groups
            
            total_verts = len(obj.data.vertices)
            for i, v in enumerate(obj.data.vertices):
                # Update progress
                if i % 100 == 0:
                    wm.progress_update(i / total_verts * 100)
                    
                groups = [vertex_groups[g.group].name for g in v.groups if g.weight > 0.0]
                if len(groups) > 1:
                    for g1, g2 in itertools.combinations(sorted(groups), 2):
                        key = (g1, g2)
                        if key not in overlaps_map:
                            overlaps_map[key] = set()
                        overlaps_map[key].add(v.index)

            for (g1, g2), verts in overlaps_map.items():
                unique_verts = sorted(verts)
                item = scene.vertex_overlap_list.add()
                item.groups = f"{g1} + {g2}"
                item.count = len(unique_verts)
                item.verts = ",".join(map(str, unique_verts))
                item.selected = False

            if len(scene.vertex_overlap_list) == 0:
                self.report({'INFO'}, "No overlapping vertex weights found")
            else:
                self.report({'INFO'}, f"Found {len(scene.vertex_overlap_list)} overlap pairs")
                
        finally:
            wm.progress_end()
            
        return {'FINISHED'}


class OBJECT_OT_select_overlap_vertices(bpy.types.Operator):
    bl_idname = "object.select_overlap_vertices"
    bl_label = "Select Affected Faces"
    bl_description = "Put mesh in Edit Mode and select all faces from chosen overlap entries"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj, error = validate_active_object(context, 'MESH')
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}

        scene = context.scene
        overlap_list = scene.vertex_overlap_list

        if not overlap_list:
            self.report({'WARNING'}, "No overlaps found. Run 'Check Vertex Overlaps' first")
            return {'CANCELLED'}

        # Collect vertices from all selected items
        indices = set()
        selected_count = 0
        
        for item in overlap_list:
            if item.selected:
                selected_count += 1
                if item.verts.strip():
                    try:
                        item_indices = [int(i) for i in item.verts.split(",") if i.strip()]
                        indices.update(item_indices)
                    except ValueError:
                        logger.warning(f"Invalid vertex indices in item: {item.groups}")

        if selected_count == 0:
            self.report({'WARNING'}, "No overlap items selected. Check the boxes next to the items you want to select")
            return {'CANCELLED'}

        if not indices:
            self.report({'WARNING'}, "No vertices found in selected overlap items")
            return {'CANCELLED'}

        # Set active object and ensure it's selected
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        
        # Ensure we're in edit mode
        if obj.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')

        # Set face select mode
        context.tool_settings.mesh_select_mode = (False, False, True)
        bpy.ops.mesh.reveal(select=False)

        me = obj.data
        bm = bmesh.from_edit_mesh(me)

        # Deselect all faces first
        for f in bm.faces:
            f.select = False

        # Select faces containing any of the overlap vertices
        selected_faces = 0
        for f in bm.faces:
            if any(v.index in indices for v in f.verts):
                f.select = True
                selected_faces += 1

        bmesh.update_edit_mesh(me, loop_triangles=False, destructive=False)

        self.report({'INFO'}, f"Selected {selected_faces} faces from {len(indices)} vertices ({selected_count} overlap groups)")
        return {'FINISHED'}


class OBJECT_OT_select_all_overlaps(bpy.types.Operator):
    bl_idname = "object.select_all_overlaps"
    bl_label = "Select All"
    bl_description = "Select all overlapping items"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        for item in scene.vertex_overlap_list:
            item.selected = True
        self.report({'INFO'}, f"Selected all {len(scene.vertex_overlap_list)} overlap items")
        return {'FINISHED'}


class OBJECT_OT_deselect_all_overlaps(bpy.types.Operator):
    bl_idname = "object.deselect_all_overlaps"
    bl_label = "Deselect All"
    bl_description = "Deselect all overlapping items"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        for item in scene.vertex_overlap_list:
            item.selected = False
        self.report({'INFO'}, "Deselected all overlap items")
        return {'FINISHED'}


class VERTEXOVERLAP_UL_list(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.prop(item, "selected", text="")
        row.label(text=f"{item.groups} — {item.count} verts")


# ------------------------------------------------------------
# TEXTURING TOOLS
# ------------------------------------------------------------
class OBJECT_OT_assign_textures_to_materials(bpy.types.Operator):
    bl_idname = "object.assign_textures_to_materials"
    bl_label = "Image Texture to Object Material"
    bl_description = "Assigns material names based on image texture node names, as well as applying the .bmp extension"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not context.selected_objects:
            self.report({'WARNING'}, "No objects selected")
            return {'CANCELLED'}

        assigned_count = 0
        for obj in context.selected_objects:
            if obj.type != "MESH":
                continue
            for mat in obj.data.materials:
                if mat and mat.node_tree:
                    for node in mat.node_tree.nodes:
                        if node.type == "TEX_IMAGE" and node.image:
                            old_name = mat.name
                            mat.name = clean_name_to_bmp(node.image.name)
                            if old_name != mat.name:
                                assigned_count += 1
                            break

        if assigned_count == 0:
            self.report({'WARNING'}, "No texture image nodes found or materials already correctly named")
        else:
            self.report({'INFO'}, f"Assigned textures to {assigned_count} materials")
        return {'FINISHED'}


class OBJECT_OT_rename_materials_bmp(bpy.types.Operator):
    bl_idname = "object.rename_materials_bmp"
    bl_label = "Force .bmp Extension"
    bl_description = "Renames all materials in selected objects to end with .bmp extension"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not context.selected_objects:
            self.report({'WARNING'}, "No objects selected")
            return {'CANCELLED'}

        renamed_count = 0
        for obj in context.selected_objects:
            if obj.type != "MESH":
                continue
            for mat in obj.data.materials:
                if mat:
                    old_name = mat.name
                    mat.name = clean_name_to_bmp(mat.name)
                    if old_name != mat.name:
                        renamed_count += 1

        if renamed_count == 0:
            self.report({'INFO'}, "All materials already have .bmp extension")
        else:
            self.report({'INFO'}, f"Renamed {renamed_count} materials to .bmp")
        return {'FINISHED'}


# ------------------------------------------------------------
# VERTEX WEIGHT QUICK FIX 
# ------------------------------------------------------------
class OBJECT_OT_vertex_weight_quickfix(bpy.types.Operator):
    bl_idname = "object.vertex_weight_quickfix"
    bl_label = "Automatic Hard Weights"
    bl_description = (
        "Automatically normalize weights, then run Quantize and Limit Total "
        "on all groups with parameter 1"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj, error = validate_active_object(context, "MESH")
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}

        if not obj.vertex_groups:
            self.report({'WARNING'}, "No vertex groups found on this mesh")
            return {'CANCELLED'}

        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)

        # Switch to Weight Paint mode
        bpy.ops.object.mode_set(mode='WEIGHT_PAINT')

        # Ensure Auto Normalize is on
        context.tool_settings.use_auto_normalize = True

        # FIXED: Use 'steps' parameter instead of 'factor'
        bpy.ops.object.vertex_group_quantize(steps=1)

        # Limit Total (keep 1 influence)
        bpy.ops.object.vertex_group_limit_total(limit=1)

        self.report({'INFO'}, "Applied Auto-Normalize, Quantize, and Limit Total (1)")
        return {'FINISHED'}


# ------------------------------------------------------------
# REMOVE UNUSED VERTEX GROUPS 
# ------------------------------------------------------------
class OBJECT_OT_remove_unused_vertex_groups(bpy.types.Operator):
    bl_idname = "object.remove_unused_vertex_groups"
    bl_label = "Clean Unassigned Vertices"
    bl_description = "Remove all empty/unused vertex groups from selected meshes"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not context.selected_objects:
            self.report({'WARNING'}, "No objects selected")
            return {'CANCELLED'}

        removed_total = 0
        
        # Store original modes
        original_modes = {}
        for obj in context.selected_objects:
            if obj.type == "MESH":
                original_modes[obj] = obj.mode
        
        try:
            # Switch all to OBJECT mode first
            for obj in context.selected_objects:
                if obj.type == "MESH" and obj.mode != 'OBJECT':
                    bpy.context.view_layer.objects.active = obj
                    bpy.ops.object.mode_set(mode='OBJECT')
            
            # Process each object
            for obj in context.selected_objects:
                if obj.type != "MESH":
                    continue
                    
                # Make this object active
                bpy.context.view_layer.objects.active = obj
                
                # Find unused vertex groups (groups with no weight data)
                unused_groups = []
                for vg in obj.vertex_groups:
                    used = False
                    for v in obj.data.vertices:
                        try:
                            # Try to get weight for this vertex group
                            vg_index = vg.index
                            for g in v.groups:
                                if g.group == vg_index and g.weight > 0.0:
                                    used = True
                                    break
                            if used:
                                break
                        except:
                            continue
                    
                    if not used:
                        unused_groups.append(vg)
                
                # Remove the unused groups
                for vg in unused_groups:
                    obj.vertex_groups.remove(vg)
                
                removed_total += len(unused_groups)
            
            # Restore original modes
            for obj, mode in original_modes.items():
                if obj.mode != mode:
                    bpy.context.view_layer.objects.active = obj
                    bpy.ops.object.mode_set(mode=mode)

        except Exception as e:
            self.report({'ERROR'}, f"Error removing vertex groups: {str(e)}")
            return {'CANCELLED'}

        if removed_total == 0:
            self.report({'INFO'}, "No unused vertex groups found")
        else:
            self.report({'INFO'}, f"Removed {removed_total} unused vertex groups from {len(context.selected_objects)} object(s)")
        return {'FINISHED'}


# ------------------------------------------------------------
# PANELS
# ------------------------------------------------------------
class VIEW3D_PT_gs_model_helper(bpy.types.Panel):
    bl_label = "Prefixes & Limbs Tools"
    bl_idname = "VIEW3D_PT_gs_model_helper"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "GS Model Helper"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props = scene.gsmodelhelper_props

        layout.label(text="Prefix Renamer", icon="OUTLINER_OB_ARMATURE")
        layout.prop(props, "vertex_from")
        layout.prop(props, "vertex_to")
        row = layout.row(align=True)
        row.operator("object.rename_prefix", icon="PLAY")
        row.operator("object.swap_inputs", icon="ARROW_LEFTRIGHT")

        layout.separator()
        layout.label(text="Swap Valve & Gearbox Limbs λ/⚙", icon="TOOL_SETTINGS")
        layout.operator("object.swap_limbs", icon="PLAY")

        layout.separator()
        layout.label(text="Right and Left Prefix Swapper", icon="AREA_SWAP")
        layout.operator("object.swap_rl_vertex_groups", text="Swap Prefix", icon="PLAY")


class VIEW3D_PT_vertex_weights(bpy.types.Panel):
    bl_label = "Vertex Weights/Groups Tools"
    bl_idname = "VIEW3D_PT_vertex_weights"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "GS Model Helper"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.label(text="Hard Weights & Cleanup", icon="GROUP_VERTEX")
        layout.operator("object.vertex_weight_quickfix", icon="MOD_VERTEX_WEIGHT")
        layout.operator("object.remove_unused_vertex_groups", icon="X")

        layout.separator()
        layout.label(text="Overlap Checker", icon="MESH_DATA")
        layout.operator("object.check_vertex_overlaps", icon="VIEWZOOM")

        if len(scene.vertex_overlap_list) > 0:
            row = layout.row(align=True)
            row.operator("object.select_all_overlaps", text="All")
            row.operator("object.deselect_all_overlaps", text="None")

        layout.template_list(
            "VERTEXOVERLAP_UL_list", "",
            scene, "vertex_overlap_list",
            scene, "vertex_overlap_index",
            rows=6
        )

        if len(scene.vertex_overlap_list) > 0:
            layout.operator("object.select_overlap_vertices", icon="RESTRICT_SELECT_OFF")
            selected_count = sum(1 for item in scene.vertex_overlap_list if item.selected)
            if selected_count > 0:
                layout.label(text=f"Selected: {selected_count}/{len(scene.vertex_overlap_list)}")


class VIEW3D_PT_texturing(bpy.types.Panel):
    bl_label = "Texturing Tools"
    bl_idname = "VIEW3D_PT_texturing"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "GS Model Helper"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props = scene.gsmodelhelper_props

        layout.label(text="Texture Interpolation", icon="MATERIAL_DATA")
        row = layout.row(align=True)
        row.operator("object.set_interp_closest", icon="TEXTURE", depress=(props.interp_mode=="CLOSEST"))
        row.operator("object.set_interp_linear", icon="NODE_TEXTURE", depress=(props.interp_mode=="LINEAR"))

        layout.separator()
        layout.label(text="Material Rename", icon="FILE_TEXT")
        layout.operator("object.assign_textures_to_materials", icon="PLAY")
        layout.operator("object.rename_materials_bmp", icon="PLAY")


# ------------------------------------------------------------
# REGISTER (FIXED)
# ------------------------------------------------------------
classes = (
    GSModelHelper,
    OBJECT_OT_swap_rl_vertex_groups,
    OBJECT_OT_rename_prefix,
    OBJECT_OT_swap_inputs,
    OBJECT_OT_swap_limbs,
    OBJECT_OT_set_interp_closest,
    OBJECT_OT_set_interp_linear,
    VertexOverlapItem,
    OBJECT_OT_check_vertex_overlaps,
    OBJECT_OT_select_overlap_vertices,
    OBJECT_OT_select_all_overlaps,
    OBJECT_OT_deselect_all_overlaps,
    VERTEXOVERLAP_UL_list,
    OBJECT_OT_vertex_weight_quickfix,
    OBJECT_OT_remove_unused_vertex_groups,
    OBJECT_OT_assign_textures_to_materials,
    OBJECT_OT_rename_materials_bmp,
    VIEW3D_PT_gs_model_helper,
    VIEW3D_PT_vertex_weights,
    VIEW3D_PT_texturing,
)

def register():
    # Register classes
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Register properties
    bpy.types.Scene.gsmodelhelper_props = bpy.props.PointerProperty(type=GSModelHelper)
    bpy.types.Scene.vertex_overlap_list = bpy.props.CollectionProperty(type=VertexOverlapItem)
    bpy.types.Scene.vertex_overlap_index = bpy.props.IntProperty(default=-1)

def unregister():
    # Unregister properties
    del bpy.types.Scene.vertex_overlap_list
    del bpy.types.Scene.vertex_overlap_index
    del bpy.types.Scene.gsmodelhelper_props
    
    # Unregister classes in reverse order
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
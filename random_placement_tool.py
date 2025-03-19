import bpy
import random
import math
import bmesh
from mathutils import Vector, Matrix
import json

# Fonction pour obtenir un point aléatoire sur la surface d'un objet
def get_random_point_on_surface(obj, seed=None):
    if seed is not None:
        random.seed(seed)
        
    bm = bmesh.new()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    mesh = obj.evaluated_get(depsgraph).to_mesh()
    bm.from_mesh(mesh)
    bm.transform(obj.matrix_world)
    bm.faces.ensure_lookup_table()
    
    if len(bm.faces) == 0:
        bm.free()
        obj.to_mesh_clear()
        return obj.location, Vector((0, 0, 1))
    
    total_area = sum(f.calc_area() for f in bm.faces)
    rand_area = random.uniform(0, total_area)
    
    cumulative_area = 0
    selected_face = None
    for face in bm.faces:
        cumulative_area += face.calc_area()
        if cumulative_area >= rand_area:
            selected_face = face
            break
    
    if not selected_face:
        selected_face = bm.faces[-1]
    
    verts = selected_face.verts
    if len(verts) == 3:  # Triangle
        a, b, c = [v.co for v in verts]
        u = random.random()
        v = random.random()
        if u + v > 1:
            u = 1 - u
            v = 1 - v
        w = 1 - u - v
        point = a * u + b * v + c * w
    else:  # Polygone (décomposé en triangles)
        center = selected_face.calc_center_median()
        i = random.randint(0, len(verts) - 1)
        a = center
        b = verts[i].co
        c = verts[(i + 1) % len(verts)].co
        
        u = random.random()
        v = random.random()
        if u + v > 1:
            u = 1 - u
            v = 1 - v
        w = 1 - u - v
        point = a * u + b * v + c * w
    
    normal = selected_face.normal
    
    bm.free()
    obj.to_mesh_clear()
    
    return point, normal

# Fonction pour mettre à jour le placement des objets
def update_placement(self, context):
    props = context.scene.random_placement_props
    
    # Vérifie si la mise à jour dynamique est activée
    if not props.dynamic_update:
        return
    
    # Met à jour chaque groupe de placement
    for group_index, group in enumerate(props.placement_groups):
        # Vérifie si l'objet source existe encore
        if not group.source_obj:
            continue
            
        # Récupère tous les objets de ce groupe
        group_objects = [obj for obj in bpy.data.objects if obj.get("random_placement_id") == group.group_id]
        
        if not group_objects:
            continue
        
        # Trouve l'objet cible
        target_obj = group.target_obj
        
        if not target_obj:
            continue
        
        # Vérifie si le nombre d'instances a changé
        current_num_instances = len(group_objects)
        if current_num_instances != group.num_instances:
            # Régénère les points et normales
            points_data = []
            for i in range(group.num_instances):
                point, normal = get_random_point_on_surface(target_obj, seed=group.random_seed + i)
                points_data.append({"point": [point.x, point.y, point.z], "normal": [normal.x, normal.y, normal.z]})
            
            # Met à jour les points stockés
            group.points_data = json.dumps(points_data)
            
            # Ajoute ou supprime des objets si nécessaire
            if current_num_instances < group.num_instances:
                # Ajoute de nouveaux objets
                for i in range(current_num_instances, group.num_instances):
                    new_obj = group.source_obj.copy()
                    new_obj.data = group.source_obj.data
                    new_obj["random_placement_id"] = group.group_id
                    new_obj["random_placement_index"] = i
                    
                    if group.collection_name:
                        bpy.data.collections[group.collection_name].objects.link(new_obj)
                    else:
                        context.scene.collection.objects.link(new_obj)
                    
                    group_objects.append(new_obj)
            else:
                # Cache les objets en excès
                for obj in group_objects[group.num_instances:]:
                    obj.hide_viewport = True
                    obj.hide_render = True
        
        # Charge les points et normales stockés
        points_data = []
        if group.points_data:
            try:
                points_data = json.loads(group.points_data)
            except:
                continue
        
        # Applique la visibilité du groupe
        for obj in group_objects:
            obj.hide_viewport = not group.is_visible
            obj.hide_render = not group.is_visible
        
        # Si le groupe n'est pas visible, passe au suivant
        if not group.is_visible:
            continue
        
        # Mise à jour des objets existants
        for i, obj in enumerate(group_objects):
            if i >= len(points_data):
                # Cache l'objet s'il dépasse le nombre d'instances disponibles
                obj.hide_viewport = True
                obj.hide_render = True
                continue
            
            # Récupère les données de point et normale
            point_data = points_data[i]
            point = Vector(point_data["point"])
            normal = Vector(point_data["normal"])
            
            # Positionne l'objet
            obj.location = point
            
            # Récupère l'index de l'objet dans le groupe
            obj_index = obj.get("random_placement_index", i)
            seed_to_use = group.random_seed + obj_index
            
            # Applique une rotation
            if group.align_to_normal:
                # Aligne l'axe Z de l'objet avec la normale de la surface
                z_axis = Vector((0, 0, 1))
                angle = z_axis.angle(normal)
                axis = z_axis.cross(normal)
                
                if axis.length > 0.001:  # Évite la division par zéro
                    axis.normalize()
                    rot_matrix = Matrix.Rotation(angle, 4, axis)
                    obj.rotation_euler = (rot_matrix.to_euler())
                    
                    # Ajoute une rotation aléatoire autour de la normale
                    random.seed(seed_to_use)
                    z_rot = math.radians(random.uniform(0, group.max_rotation_z))
                    obj.rotation_euler.rotate_axis('Z', z_rot)
            else:
                # Rotation complètement aléatoire
                random.seed(seed_to_use)
                obj.rotation_euler = (
                    math.radians(random.uniform(0, group.max_rotation_x)),
                    math.radians(random.uniform(0, group.max_rotation_y)),
                    math.radians(random.uniform(0, group.max_rotation_z))
                )
            
            # Applique une échelle aléatoire
            random.seed(seed_to_use + 1000)  # Seed différent pour l'échelle
            if group.uniform_scale:
                scale_factor = random.uniform(group.scale_min, group.scale_max)
                obj.scale = (scale_factor, scale_factor, scale_factor)
            else:
                obj.scale = (
                    random.uniform(group.scale_min, group.scale_max),
                    random.uniform(group.scale_min, group.scale_max),
                    random.uniform(group.scale_min, group.scale_max)
                )

# Structure pour stocker les paramètres d'un groupe de placement
class PlacementGroupSettings(bpy.types.PropertyGroup):
    # Identifiant unique du groupe
    group_id: bpy.props.IntProperty(default=0)
    
    # Propriétés de rotation
    max_rotation_x: bpy.props.FloatProperty(
        name="Max X Rotation",
        description="Maximum rotation in X axis (degrees)",
        default=360.0,
        min=0.0,
        max=360.0,
        update=update_placement
    )
    
    max_rotation_y: bpy.props.FloatProperty(
        name="Max Y Rotation",
        description="Maximum rotation in Y axis (degrees)",
        default=360.0,
        min=0.0,
        max=360.0,
        update=update_placement
    )
    
    max_rotation_z: bpy.props.FloatProperty(
        name="Max Z Rotation",
        description="Maximum rotation in Z axis (degrees)",
        default=360.0,
        min=0.0,
        max=360.0,
        update=update_placement
    )
    
    align_to_normal: bpy.props.BoolProperty(
        name="Align to Surface",
        description="Align objects to the surface normal",
        default=True,
        update=update_placement
    )
    
    # Propriétés d'échelle
    scale_min: bpy.props.FloatProperty(
        name="Minimum Scale",
        description="Minimum random scale factor",
        default=0.8,
        min=0.1,
        max=10.0,
        update=update_placement
    )
    
    scale_max: bpy.props.FloatProperty(
        name="Maximum Scale",
        description="Maximum random scale factor",
        default=1.2,
        min=0.1,
        max=10.0,
        update=update_placement
    )
    
    uniform_scale: bpy.props.BoolProperty(
        name="Uniform Scale",
        description="Apply the same scale to all axes",
        default=True,
        update=update_placement
    )
    
    # Propriétés de l'objet source
    source_obj: bpy.props.PointerProperty(type=bpy.types.Object)
    target_obj: bpy.props.PointerProperty(type=bpy.types.Object)
    
    # Propriétés de placement
    num_instances: bpy.props.IntProperty(
        name="Number of Instances",
        description="Number of instances to create",
        default=10,
        min=1,
        max=1000,
        update=update_placement
    )
    
    # Stockage des points et normales
    points_data: bpy.props.StringProperty(default="")
    
    # Nom de la collection
    collection_name: bpy.props.StringProperty(default="")
    
    # Visibilité du groupe
    is_visible: bpy.props.BoolProperty(default=True)
    
    # Seed pour la génération aléatoire
    random_seed: bpy.props.IntProperty(default=0)

# Classe pour stocker les propriétés globales
class RandomPlacementProperties(bpy.types.PropertyGroup):
    # Propriété pour activer/désactiver la mise à jour dynamique
    dynamic_update: bpy.props.BoolProperty(
        name="Dynamic Update",
        description="Update the placement in real-time when changing parameters",
        default=True
    )
    
    # Propriété pour préserver les placements précédents
    preserve_previous: bpy.props.BoolProperty(
        name="Preserve Previous Placements",
        description="Keep previous placements when adding new objects",
        default=False
    )
    
    # Propriété pour grouper dans une collection
    use_collection: bpy.props.BoolProperty(
        name="Group in Collection",
        description="Group all instances in a new collection",
        default=True
    )
    
    # Nombre d'instances pour le nouveau placement
    num_instances: bpy.props.IntProperty(
        name="Number of Instances",
        description="Number of instances to create",
        default=10,
        min=1,
        max=1000
    )
    
    # Propriétés pour stocker temporairement les objets source et cible
    source_obj: bpy.props.PointerProperty(type=bpy.types.Object)
    target_obj: bpy.props.PointerProperty(type=bpy.types.Object)
    
    # Groupe actif pour l'édition
    active_group_index: bpy.props.IntProperty(default=0)
    
    # Liste des groupes de placement
    placement_groups: bpy.props.CollectionProperty(type=PlacementGroupSettings)
    
    # Compteur pour générer des IDs uniques
    next_group_id: bpy.props.IntProperty(default=1)

# Opérateur pour placer aléatoirement des objets
class RandomLinkedPlacementOperator(bpy.types.Operator):
    """Place randomly linked duplicates of the first selected object on the second selected object"""
    bl_idname = "object.random_linked_placement"
    bl_label = "Execute Random Placement"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        # Vérifie qu'il y a exactement deux objets sélectionnés
        return len(context.selected_objects) == 2
    
    def execute(self, context):
        props = context.scene.random_placement_props
        
        if len(context.selected_objects) != 2:
            self.report({'ERROR'}, "Exactly two objects must be selected")
            return {'CANCELLED'}
        
        # Identifie les objets source et cible
        selected_objects = context.selected_objects.copy()
        target_obj = context.active_object
        source_obj = [obj for obj in selected_objects if obj != target_obj][0]
        
        # Vérifie que l'objet cible a une géométrie
        if target_obj.type != 'MESH':
            self.report({'ERROR'}, "Target object must be a mesh")
            return {'CANCELLED'}
        
        # Stocke les objets source et cible dans les propriétés temporaires
        props.source_obj = source_obj
        props.target_obj = target_obj
        
        # Génère un nouveau seed aléatoire
        new_seed = random.randint(0, 1000000)
        
        # Crée un nouveau groupe de placement
        new_group = props.placement_groups.add()
        new_group.group_id = props.next_group_id
        props.next_group_id += 1
        
        # Configure le nouveau groupe
        new_group.source_obj = source_obj
        new_group.target_obj = target_obj
        new_group.num_instances = props.num_instances
        new_group.random_seed = new_seed
        new_group.is_visible = True
        
        # Copie les paramètres par défaut
        new_group.align_to_normal = True
        new_group.max_rotation_x = 360.0
        new_group.max_rotation_y = 360.0
        new_group.max_rotation_z = 360.0
        new_group.scale_min = 0.8
        new_group.scale_max = 1.2
        new_group.uniform_scale = True
        
        # Crée une nouvelle collection si demandé
        collection_name = f"RandomPlacement_{source_obj.name}_{new_group.random_seed}"
        if props.use_collection:
            new_collection = bpy.data.collections.new(collection_name)
            bpy.context.scene.collection.children.link(new_collection)
            new_group.collection_name = collection_name
        
        # Génère et stocke les points et normales
        points_data = []
        for i in range(new_group.num_instances):
            point, normal = get_random_point_on_surface(target_obj, seed=new_group.random_seed + i)
            points_data.append({"point": [point.x, point.y, point.z], "normal": [normal.x, normal.y, normal.z]})
        
        # Stocke les points et normales au format JSON
        new_group.points_data = json.dumps(points_data)
        
        # Crée les duplications liées
        created_objects = []
        for i in range(new_group.num_instances):
            # Crée une duplication liée de l'objet source
            new_obj = source_obj.copy()
            # Partage les mêmes données d'objet (mesh data)
            new_obj.data = source_obj.data
            
            # Marque l'objet comme créé par ce script avec l'ID du groupe
            new_obj["random_placement_id"] = new_group.group_id
            new_obj["random_placement_index"] = i
            
            # Ajoute l'objet à la collection appropriée
            if props.use_collection and new_group.collection_name:
                bpy.data.collections[new_group.collection_name].objects.link(new_obj)
            else:
                context.scene.collection.objects.link(new_obj)
            
            created_objects.append(new_obj)
        
        # Définit le groupe actif
        props.active_group_index = len(props.placement_groups) - 1
        
        # Applique le placement initial
        update_placement(props, context)
        
        # Sélectionne tous les objets créés
        bpy.ops.object.select_all(action='DESELECT')
        for obj in created_objects:
            obj.select_set(True)
        
        # Définit l'objet actif
        if created_objects:
            context.view_layer.objects.active = created_objects[0]
        
        self.report({'INFO'}, f"Created {new_group.num_instances} linked duplicates in group {new_group.group_id}")
        return {'FINISHED'}

# Opérateur pour supprimer tous les objets créés
class ClearRandomPlacementOperator(bpy.types.Operator):
    """Clear all objects created by Random Placement"""
    bl_idname = "object.clear_random_placement"
    bl_label = "Clear All"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        props = context.scene.random_placement_props
        
        # Supprime les objets existants créés par ce script
        for obj in bpy.data.objects:
            if obj.get("random_placement_id") is not None:
                bpy.data.objects.remove(obj, do_unlink=True)
        
        # Supprime les collections existantes créées par ce script
        for coll in bpy.data.collections:
            if coll.name.startswith("RandomPlacement_"):
                bpy.data.collections.remove(coll)
        
        # Réinitialise les propriétés
        props.source_obj = None
        props.target_obj = None
        props.placement_groups.clear()
        props.active_group_index = 0
        props.next_group_id = 1
        
        self.report({'INFO'}, "Cleared all random placement objects")
        return {'FINISHED'}

# Opérateur pour supprimer un groupe spécifique
class RemoveGroupOperator(bpy.types.Operator):
    """Remove a specific placement group"""
    bl_idname = "object.remove_placement_group"
    bl_label = "Remove Group"
    bl_options = {'REGISTER', 'UNDO'}
    
    group_index: bpy.props.IntProperty()
    
    def execute(self, context):
        props = context.scene.random_placement_props
        
        if self.group_index >= len(props.placement_groups):
            self.report({'ERROR'}, "Invalid group index")
            return {'CANCELLED'}
        
        # Récupère le groupe à supprimer
        group = props.placement_groups[self.group_index]
        group_id = group.group_id
        
        # Supprime les objets de ce groupe
        objects_to_remove = []
        for obj in bpy.data.objects:
            if obj.get("random_placement_id") == group_id:
                objects_to_remove.append(obj)
        
        for obj in objects_to_remove:
            bpy.data.objects.remove(obj, do_unlink=True)
        
        # Supprime la collection associée si elle existe
        if group.collection_name:
            if group.collection_name in bpy.data.collections:
                bpy.data.collections.remove(bpy.data.collections[group.collection_name])
        
        # Supprime le groupe
        props.placement_groups.remove(self.group_index)
        
        # Ajuste l'index actif
        if props.active_group_index >= len(props.placement_groups):
            props.active_group_index = max(0, len(props.placement_groups) - 1)
        
        self.report({'INFO'}, f"Removed placement group {group_id}")
        return {'FINISHED'}

# Opérateur pour dupliquer un groupe
class DuplicateGroupOperator(bpy.types.Operator):
    """Duplicate a placement group"""
    bl_idname = "object.duplicate_placement_group"
    bl_label = "Duplicate Group"
    bl_options = {'REGISTER', 'UNDO'}
    
    group_index: bpy.props.IntProperty()
    
    def execute(self, context):
        props = context.scene.random_placement_props
        
        if self.group_index >= len(props.placement_groups):
            self.report({'ERROR'}, "Invalid group index")
            return {'CANCELLED'}
        
        # Récupère le groupe à dupliquer
        source_group = props.placement_groups[self.group_index]
        
        if not source_group.source_obj:
            self.report({'ERROR'}, "Source object no longer exists")
            return {'CANCELLED'}
        
        # Crée un nouveau groupe
        new_group = props.placement_groups.add()
        new_group.group_id = props.next_group_id
        props.next_group_id += 1
        
        # Copie les propriétés du groupe source
        new_group.source_obj = source_group.source_obj
        new_group.target_obj = source_group.target_obj
        new_group.num_instances = source_group.num_instances
        new_group.align_to_normal = source_group.align_to_normal
        new_group.max_rotation_x = source_group.max_rotation_x
        new_group.max_rotation_y = source_group.max_rotation_y
        new_group.max_rotation_z = source_group.max_rotation_z
        new_group.scale_min = source_group.scale_min
        new_group.scale_max = source_group.scale_max
        new_group.uniform_scale = source_group.uniform_scale
        new_group.is_visible = source_group.is_visible
        
        # Génère un nouveau seed
        new_group.random_seed = random.randint(0, 1000000)
        
        # Charge les points et normales du groupe source
        points_data = []
        if source_group.points_data:
            try:
                points_data = json.loads(source_group.points_data)
            except:
                self.report({'ERROR'}, "Could not parse source group data")
                return {'CANCELLED'}
        
        # Crée une nouvelle collection
        collection_name = f"RandomPlacement_{source_group.source_obj.name}_{new_group.random_seed}"
        if props.use_collection:
            new_collection = bpy.data.collections.new(collection_name)
            bpy.context.scene.collection.children.link(new_collection)
            new_group.collection_name = collection_name
        
        # Stocke les points et normales
        new_group.points_data = source_group.points_data
        
        # Crée les duplications liées
        created_objects = []
        for i in range(new_group.num_instances):
            if i >= len(points_data):
                break
                
            # Crée une duplication liée de l'objet source
            new_obj = source_group.source_obj.copy()
            new_obj.data = source_group.source_obj.data
            
            # Marque l'objet comme créé par ce script avec l'ID du groupe
            new_obj["random_placement_id"] = new_group.group_id
            new_obj["random_placement_index"] = i
            
            # Ajoute l'objet à la collection appropriée
            if props.use_collection and new_group.collection_name:
                bpy.data.collections[new_group.collection_name].objects.link(new_obj)
            else:
                context.scene.collection.objects.link(new_obj)
            
            created_objects.append(new_obj)
        
        # Définit le groupe actif
        props.active_group_index = len(props.placement_groups) - 1
        
        # Applique le placement initial
        update_placement(props, context)
        
        # Sélectionne tous les objets créés
        bpy.ops.object.select_all(action='DESELECT')
        for obj in created_objects:
            obj.select_set(True)
        
        # Définit l'objet actif
        if created_objects:
            context.view_layer.objects.active = created_objects[0]
        
        self.report({'INFO'}, f"Duplicated group {source_group.group_id} to new group {new_group.group_id}")
        return {'FINISHED'}

# Opérateur pour changer la visibilité d'un groupe
class ToggleGroupVisibilityOperator(bpy.types.Operator):
    """Toggle visibility of a placement group"""
    bl_idname = "object.toggle_group_visibility"
    bl_label = "Toggle Visibility"
    bl_options = {'REGISTER', 'UNDO'}
    
    group_index: bpy.props.IntProperty()
    
    def execute(self, context):
        props = context.scene.random_placement_props
        
        if self.group_index >= len(props.placement_groups):
            self.report({'ERROR'}, "Invalid group index")
            return {'CANCELLED'}
        
        # Inverse la visibilité du groupe
        group = props.placement_groups[self.group_index]
        group.is_visible = not group.is_visible
        
        # Met à jour les objets
        update_placement(props, context)
        
        return {'FINISHED'}

# Opérateur pour régénérer un placement avec un nouveau seed
class RegenerateGroupOperator(bpy.types.Operator):
    """Regenerate placement with a new random seed"""
    bl_idname = "object.regenerate_placement"
    bl_label = "Regenerate"
    bl_options = {'REGISTER', 'UNDO'}
    
    group_index: bpy.props.IntProperty()
    
    def execute(self, context):
        props = context.scene.random_placement_props
        
        if self.group_index >= len(props.placement_groups):
            self.report({'ERROR'}, "Invalid group index")
            return {'CANCELLED'}
        
        group = props.placement_groups[self.group_index]
        
        if not group.source_obj:
            self.report({'ERROR'}, "Source object no longer exists")
            return {'CANCELLED'}
        
        # Génère un nouveau seed
        group.random_seed = random.randint(0, 1000000)
        
        # Met à jour le placement
        update_placement(props, context)
        
        self.report({'INFO'}, f"Regenerated placement for group {group.group_id}")
        return {'FINISHED'}

# Panneau pour afficher les propriétés
class RandomPlacementPanel(bpy.types.Panel):
    """Panel for Random Placement"""
    bl_label = "Random Placement"
    bl_idname = "OBJECT_PT_random_placement"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Tool'
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.random_placement_props
        
        # Section pour créer un nouveau placement
        box = layout.box()
        box.label(text="Create New Placement")
        
        # Nombre d'instances pour le nouveau placement
        box.prop(props, "num_instances")
        
        # Options globales
        box.prop(props, "use_collection")
        box.prop(props, "preserve_previous")
        box.prop(props, "dynamic_update")
        
        # Bouton pour exécuter le placement
        row = box.row()
        row.scale_y = 1.5
        row.operator("object.random_linked_placement", text="Execute Placement", icon='OUTLINER_OB_POINTCLOUD')
        
        # Bouton pour tout supprimer
        row = box.row()
        row.operator("object.clear_random_placement", text="Clear All Placements", icon='TRASH')
        
        # Affichage des groupes de placement
        if len(props.placement_groups) > 0:
            box = layout.box()
            box.label(text="Placement Groups", icon='OUTLINER_OB_GROUP_INSTANCE')
            
            # Liste des groupes
            for i, group in enumerate(props.placement_groups):
                # Cadre pour chaque groupe
                group_box = box.box()
                
                # En-tête du groupe avec boutons d'action
                header_row = group_box.row()
                
                # Nom du groupe et source
                source_name = group.source_obj.name if group.source_obj else "<Missing>"
                header_row.label(text=f"Group {group.group_id}: {source_name} ({group.num_instances})", icon='OUTLINER_OB_EMPTY')
                
                # Boutons d'action
                action_row = header_row.row(align=True)
                action_row.alignment = 'RIGHT'
                
                # Bouton de visibilité
                vis_icon = 'HIDE_OFF' if group.is_visible else 'HIDE_ON'
                op = action_row.operator("object.toggle_group_visibility", text="", icon=vis_icon)
                op.group_index = i
                
                # Bouton pour régénérer
                op = action_row.operator("object.regenerate_placement", text="", icon='FILE_REFRESH')
                op.group_index = i
                
                # Bouton pour dupliquer
                op = action_row.operator("object.duplicate_placement_group", text="", icon='DUPLICATE')
                op.group_index = i
                
                # Bouton pour supprimer
                op = action_row.operator("object.remove_placement_group", text="", icon='X')
                op.group_index = i
                
                # Si c'est le groupe actif, affiche ses paramètres
                if i == props.active_group_index and group.is_visible:
                    # Paramètres de rotation
                    rot_box = group_box.box()
                    rot_box.label(text="Rotation Settings", icon='DRIVER_ROTATIONAL_DIFFERENCE')
                    rot_box.prop(group, "align_to_normal")
                    if not group.align_to_normal:
                        rot_box.prop(group, "max_rotation_x")
                        rot_box.prop(group, "max_rotation_y")
                    rot_box.prop(group, "max_rotation_z")
                    
                    # Paramètres d'échelle
                    scale_box = group_box.box()
                    scale_box.label(text="Scale Settings", icon='FULLSCREEN_ENTER')
                    scale_box.prop(group, "uniform_scale")
                    scale_box.prop(group, "scale_min")
                    scale_box.prop(group, "scale_max")
                    
                    # Bouton pour appliquer les modifications
                    apply_row = group_box.row()
                    apply_row.scale_y = 1.2
                    apply_row.operator("object.update_placement", text="Apply Changes", icon='CHECKMARK')

# Opérateur pour mettre à jour le placement
class UpdatePlacementOperator(bpy.types.Operator):
    """Update placement with current settings"""
    bl_idname = "object.update_placement"
    bl_label = "Update Placement"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        props = context.scene.random_placement_props
        update_placement(props, context)
        return {'FINISHED'}

# Enregistrement des classes
classes = (
    PlacementGroupSettings,
    RandomPlacementProperties,
    RandomLinkedPlacementOperator,
    ClearRandomPlacementOperator,
    RemoveGroupOperator,
    DuplicateGroupOperator,
    ToggleGroupVisibilityOperator,
    RegenerateGroupOperator,
    UpdatePlacementOperator,
    RandomPlacementPanel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.random_placement_props = bpy.props.PointerProperty(type=RandomPlacementProperties)

def unregister():
    del bpy.types.Scene.random_placement_props
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()

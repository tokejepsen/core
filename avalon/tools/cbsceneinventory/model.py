from collections import defaultdict

from ... import api, io, style
from ...vendor.Qt import QtCore, QtGui
from ...vendor import qtawesome as qta

# todo(roy): refactor loading from other tools
from ..cbloader import lib as cbloader_lib
from ..projectmanager.model import (
    TreeModel, Node
)


class InventoryModel(TreeModel):
    """The model for the inventory"""

    COLUMNS = ["name", "version", "count", "family", "objectName"]

    OUTDATED_COLOR = QtGui.QColor(235, 30, 30)

    UniqueRole = QtCore.Qt.UserRole + 2     # unique label role

    def __init__(self, parent=None):
        super(InventoryModel, self).__init__(parent)
        self._hierarchy_view = False

    def data(self, index, role):

        if not index.isValid():
            return

        if role == QtCore.Qt.FontRole:
            # Make top-level entries bold
            parent = index.parent()
            if not parent.isValid():
                font = QtGui.QFont()
                font.setBold(True)
                return font

        node = index.internalPointer()
        if role == QtCore.Qt.ForegroundRole:
            # Set the text color to the OUTDATED_COLOR when the
            # collected version is not the same as the highest version
            parent = index.parent()
            if not parent.isValid():
                key = self.COLUMNS[index.column()]
                if key == "version":  # version
                    version = node.get("version", None)
                    highest = node.get("highest_version", None)
                    if version != highest:
                        return self.OUTDATED_COLOR

        # Add icons
        if role == QtCore.Qt.DecorationRole:
            if index.column() == 0:
                # Override color
                color = node.get("color", style.colors.default)
                if node.get("isGroupNode"):  # group-item
                    return qta.icon("fa.folder", color=color)
                else:
                    return qta.icon("fa.file-o", color=color)

            if index.column() == 3:
                # Family icon
                return node.get("familyIcon", None)

        if role == self.UniqueRole:
            return node['representation'] + node.get("objectName", "<none>")

        return super(InventoryModel, self).data(index, role)

    def set_hierarchy_view(self, state):
        """Set whether to display subsets in hierarchy view."""
        state = bool(state)

        if state != self._hierarchy_view:
            self._hierarchy_view = state
            self.refresh()

    def refresh(self):
        """Refresh the model"""

        host = api.registered_host()
        items = host.ls()

        self.clear()

        if self._hierarchy_view:

            items = list(items)  # construct the generator results
            parents = [self._root_node]
            while items:
                _parents = list()

                for parent in parents:
                    _unparented = list()

                    def _children():
                        """Child item provider"""
                        for item in items:
                            if item.get("parent") == parent.get("objectName"):
                                yield item
                            else:
                                # Not current parent's child, try next
                                _unparented.append(item)

                    self.add_items(_children(), parent)

                    items[:] = _unparented

                    # Parents of next level
                    for group_node in parent.children():
                        _parents += group_node.children()

                parents[:] = _parents

        else:
            self.add_items(items)

    def add_items(self, items, parent=None):
        """Add the items to the model.

        The items should be formatted similar to `api.ls()` returns, an item
        is then represented as:
            {"filename_v001.ma": [full/filename/of/loaded/filename_v001.ma,
                                  full/filename/of/loaded/filename_v001.ma],
             "nodetype" : "reference",
             "node": "referenceNode1"}

        Note: When performing an additional call to `add_items` it will *not*
            group the new items with previously existing item groups of the
            same type.

        Args:
            items (generator): the items to be processed as returned by `ls()`

        Returns:
            node.Node: root node which has children added based on the data
        """

        self.beginResetModel()

        # Group by representation
        grouped = defaultdict(list)
        for item in items:
            grouped[item['representation']].append(item)

        # Add to model
        for representation_id, group_items in sorted(grouped.items()):

            # Get parenthood per group
            representation = io.find_one({
                "_id": io.ObjectId(representation_id)
            })
            version = io.find_one({"_id": representation["parent"]})
            subset = io.find_one({"_id": version["parent"]})
            asset = io.find_one({"_id": subset["parent"]})

            # Get the primary family
            family = version['data'].get("family", "")
            if not family:
                families = version['data'].get("families", [])
                if families:
                    family = families[0]

            # Get the label and icon for the family if in configuration
            family_config = cbloader_lib.get(cbloader_lib.FAMILY_CONFIG,
                                             family)
            family = family_config.get("label", family)
            family_icon = family_config.get("icon", None)

            # Store the highest available version so the model can know
            # whether current version is currently up-to-date.
            highest_version = io.find_one({
                "type": "version",
                "parent": version["parent"]
            }, sort=[("name", -1)])

            # create the group header
            group_node = Node()
            group_node["name"] = "%s_%s: (%s)" % (asset['name'],
                                                  subset['name'],
                                                  representation["name"])
            group_node["representation"] = representation_id
            group_node["version"] = version['name']
            group_node["highest_version"] = highest_version['name']
            group_node["family"] = family
            group_node["familyIcon"] = family_icon
            group_node["count"] = len(group_items)
            group_node["isGroupNode"] = True

            self.add_child(group_node, parent=parent)

            for item in group_items:
                item_node = Node()
                item_node.update(item)

                # store the current version on the item
                item_node["version"] = version['name']

                self.add_child(item_node, parent=group_node)

        self.endResetModel()

        return self._root_node

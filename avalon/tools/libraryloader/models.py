import collections
import logging
import copy

from .. import models as tools_models
from ..loader import model as loader_models
from ..models import TreeModel, Item
from . import lib
from ...lib import MasterVersionType
from ... import style

from ...vendor import qtawesome
from ...vendor.Qt import QtCore

log = logging.getLogger(__name__)


class TasksModel(tools_models.TasksModel):
    """A model listing the tasks combined for a list of assets."""

    Columns = ["name", "count"]

    def __init__(self, dbcon, parent=None):
        self.dbcon = dbcon
        super(TasksModel, self).__init__(parent=parent)

    def _get_task_icons(self):
        # Get the project configured icons from database
        project = self.dbcon.find_one({"type": "project"})
        tasks = project["config"].get("tasks", [])
        for task in tasks:
            icon_name = task.get("icon", None)
            if icon_name:
                icon = qtawesome.icon(
                    "fa.{}".format(icon_name),
                    color=style.colors.default
                )
                self._icons[task["name"]] = icon

    def set_assets(self, asset_ids=[], asset_entities=None):
        """Set assets to track by their database id.

        Arguments:
            asset_ids (list): List of asset ids.
            asset_entities (list): List of asset entities from MongoDB.
        """
        assets = list()
        if asset_entities is not None:
            assets = asset_entities
        else:
            # prepare filter query
            or_query = [{"_id": asset_id} for asset_id in asset_ids]
            _filter = {"type": "asset", "$or": or_query}

            # find assets in db by query
            assets = [asset for asset in self.dbcon.find_one(_filter)]
            db_assets_ids = [asset["_id"] for asset in assets]

            # check if all assets were found
            not_found = [
                str(a_id) for a_id in asset_ids if a_id not in db_assets_ids
            ]

            assert not not_found, "Assets not found by id: {0}".format(
                ", ".join(not_found)
            )

        self._num_assets = len(assets)

        tasks = collections.Counter()
        for asset in assets:
            asset_tasks = asset.get("data", {}).get("tasks", [])
            tasks.update(asset_tasks)

        self.clear()
        self.beginResetModel()

        default_icon = self._icons["__default__"]

        if not tasks:
            no_task_icon = self._icons["__no_task__"]
            item = Item({
                "name": "No task",
                "count": 0,
                "icon": no_task_icon,
                "enabled": False,
            })

            self.add_child(item)

        else:
            for task, count in sorted(tasks.items()):
                icon = self._icons.get(task, default_icon)

                item = Item({
                    "name": task,
                    "count": count,
                    "icon": icon
                })

                self.add_child(item)

        self.endResetModel()


class SubsetsModel(loader_models.SubsetsModel):
    def __init__(self, dbcon, grouping=True, parent=None):
        self.dbcon = dbcon
        super(SubsetsModel, self).__init__(grouping=grouping, parent=parent)

    def setData(self, index, value, role=QtCore.Qt.EditRole):

        # Trigger additional edit when `version` column changed
        # because it also updates the information in other columns
        if index.column() == self.Columns.index("version"):
            item = index.internalPointer()
            parent = item["_id"]
            if isinstance(value, MasterVersionType):
                versions = list(self.dbcon.find({
                    "type": {"$in": ["version", "master_version"]},
                    "parent": parent
                }, sort=[("name", -1)]))

                version = None
                last_version = None
                for __version in versions:
                    if __version["type"] == "master_version":
                        version = __version
                    elif last_version is None:
                        last_version = __version

                    if version is not None and last_version is not None:
                        break

                _version = None
                for __version in versions:
                    if __version["_id"] == version["version_id"]:
                        _version = __version
                        break

                version["data"] = _version["data"]
                version["name"] = _version["name"]
                version["is_from_latest"] = (
                    last_version["_id"] == _version["_id"]
                )

            else:
                version = self.dbcon.find_one({
                    "name": value,
                    "type": "version",
                    "parent": parent
                })

            self.set_version(index, version)

        # Use super of TreeModel not SubsetsModel from loader!!
        # - he would do the same but with current io context
        return super(loader_models.SubsetsModel, self).setData(
            index, value, role
        )

    def set_version(self, index, version):
        """Update the version data of the given index.

        Arguments:
            index (QtCore.QModelIndex): The model index.
            version (dict) Version document in the database.

        """

        assert isinstance(index, QtCore.QModelIndex)
        if not index.isValid():
            return

        item = index.internalPointer()

        assert version["parent"] == item["_id"], (
            "Version does not belong to subset"
        )

        # Get the data from the version
        version_data = version.get("data", dict())

        # Compute frame ranges (if data is present)
        frame_start = version_data.get(
            "frameStart",
            # backwards compatibility
            version_data.get("startFrame", None)
        )
        frame_end = version_data.get(
            "frameEnd",
            # backwards compatibility
            version_data.get("endFrame", None)
        )

        handle_start = version_data.get("handleStart", None)
        handle_end = version_data.get("handleEnd", None)
        if handle_start is not None and handle_end is not None:
            handles = "{}-{}".format(str(handle_start), str(handle_end))
        else:
            handles = version_data.get("handles", None)

        if frame_start is not None and frame_end is not None:
            # Remove superfluous zeros from numbers (3.0 -> 3) to improve
            # readability for most frame ranges
            start_clean = ("%f" % frame_start).rstrip("0").rstrip(".")
            end_clean = ("%f" % frame_end).rstrip("0").rstrip(".")
            frames = "{0}-{1}".format(start_clean, end_clean)
            duration = frame_end - frame_start + 1
        else:
            frames = None
            duration = None

        if item["schema"] == "avalon-core:subset-3.0":
            families = item["data"]["families"]
        else:
            families = version_data.get("families", [None])

        family = families[0]
        family_config = lib.get_family_cached_config(family)

        item.update({
            "version": version["name"],
            "version_document": version,
            "author": version_data.get("author", None),
            "time": version_data.get("time", None),
            "family": family,
            "familyLabel": family_config.get("label", family),
            "familyIcon": family_config.get("icon", None),
            "families": set(families),
            "frameStart": frame_start,
            "frameEnd": frame_end,
            "duration": duration,
            "handles": handles,
            "frames": frames,
            "step": version_data.get("step", None)
        })

    def _fetch(self):
        asset_docs = self.dbcon.find({
            "type": "asset",
            "_id": {"$in": self._asset_ids}
        })
        asset_docs_by_id = {
            asset_doc["_id"]: asset_doc
            for asset_doc in asset_docs
        }

        subset_docs_by_id = {}
        for subset in self.dbcon.find({
            "type": "subset",
            "parent": {"$in": self._asset_ids}
        }):
            if self._doc_fetching_stop:
                return
            subset_docs_by_id[subset["_id"]] = subset

        subset_ids = list(subset_docs_by_id.keys())
        _pipeline = [
            # Find all versions of those subsets
            {"$match": {
                "type": "version",
                "parent": {"$in": subset_ids}
            }},
            # Sorting versions all together
            {"$sort": {"name": 1}},
            # Group them by "parent", but only take the last
            {"$group": {
                "_id": "$parent",
                "_version_id": {"$last": "$_id"},
                "name": {"$last": "$name"},
                "type": {"$last": "$type"},
                "data": {"$last": "$data"},
                "locations": {"$last": "$locations"},
                "schema": {"$last": "$schema"}
            }}
        ]
        last_versions_by_subset_id = dict()
        for doc in self.dbcon.aggregate(_pipeline):
            if self._doc_fetching_stop:
                return
            doc["parent"] = doc["_id"]
            doc["_id"] = doc.pop("_version_id")
            last_versions_by_subset_id[doc["parent"]] = doc

        master_versions = self.dbcon.find({
            "type": "master_version",
            "parent": {"$in": subset_ids}
        })
        missing_versions = []
        for master_version in master_versions:
            version_id = master_version["version_id"]
            if version_id not in last_versions_by_subset_id:
                missing_versions.append(version_id)

        missing_versions_by_id = {}
        if missing_versions:
            missing_version_docs = self.dbcon.find({
                "type": "version",
                "_id": {"$in": missing_versions}
            })
            missing_versions_by_id = {
                missing_version_doc["_id"]: missing_version_doc
                for missing_version_doc in missing_version_docs
            }

        for master_version in master_versions:
            version_id = master_version["version_id"]
            subset_id = master_version["parent"]

            version_doc = last_versions_by_subset_id.get(subset_id)
            if version_doc is None:
                version_doc = missing_versions_by_id.get(version_id)
                if version_doc is None:
                    continue

            master_version["data"] = version_doc["data"]
            master_version["name"] = MasterVersionType(version_doc["name"])
            # Add information if master version is from latest version
            master_version["is_from_latest"] = version_id == version_doc["_id"]

            last_versions_by_subset_id[subset_id] = master_version

        self._doc_payload = {
            "asset_docs_by_id": asset_docs_by_id,
            "subset_docs_by_id": subset_docs_by_id,
            "last_versions_by_subset_id": last_versions_by_subset_id
        }
        self.doc_fetched.emit()

    def on_doc_fetched(self):
        self.clear()
        self.beginResetModel()

        active_groups = []
        for asset_id in self._asset_ids:
            result = lib.get_active_group_config(self.dbcon, asset_id)
            if result:
                active_groups.extend(result)

        asset_docs_by_id = self._doc_payload.get(
            "asset_docs_by_id"
        )
        subset_docs_by_id = self._doc_payload.get(
            "subset_docs_by_id"
        )
        last_versions_by_subset_id = self._doc_payload.get(
            "last_versions_by_subset_id"
        )
        if (
            asset_docs_by_id is None
            or subset_docs_by_id is None
            or last_versions_by_subset_id is None
            or len(self._asset_ids) == 0
        ):
            self.endResetModel()
            self.refreshed.emit(False)
            return

        self._fill_subset_items(
            asset_docs_by_id, subset_docs_by_id, last_versions_by_subset_id
        )

    def split_for_group(self, subset_docs):
        """Collect all active groups from each subset"""
        predefineds = lib.GROUP_CONFIG_CACHE.copy()
        default_group_config = predefineds.pop("__default__")

        _orders = set([0])  # default order zero included
        for config in predefineds.values():
            _orders.add(config["order"])

        # Remap order to list index
        orders = sorted(_orders)

        subset_docs_without_group = collections.defaultdict(list)
        subset_docs_by_group = collections.defaultdict(dict)
        for subset_doc in subset_docs:
            subset_name = subset_doc["name"]
            if self._grouping:
                group_name = subset_doc["data"].get("subsetGroup")
                if group_name:
                    if subset_name not in subset_docs_by_group[group_name]:
                        subset_docs_by_group[group_name][subset_name] = []

                    subset_docs_by_group[group_name][subset_name].append(
                        subset_doc
                    )
                    continue

            subset_docs_without_group[subset_name].append(subset_doc)

        _groups = list()
        for name in subset_docs_by_group.keys():
            # Get group config
            config = predefineds.get(name, default_group_config)
            # Base order
            remapped_order = orders.index(config["order"])

            data = {
                "name": name,
                "icon": config["icon"],
                "_order": remapped_order,
            }

            _groups.append(data)

        # Sort by tuple (base_order, name)
        # If there are multiple groups in same order, will sorted by name.
        ordered_groups = sorted(
            _groups, key=lambda _group: (_group.pop("_order"), _group["name"])
        )

        total = len(ordered_groups)
        order_temp = "%0{}d".format(len(str(total)))

        groups = {}
        # Update sorted order to config
        for order, data in enumerate(ordered_groups):
            data.update({
                # Format orders into fixed length string for groups sorting
                "order": "0" + order_temp % order,
                "inverseOrder": "2" + order_temp % (total - order)
            })
            groups[data["name"]] = data

        return groups, subset_docs_without_group, subset_docs_by_group

    def create_multiasset_group(
        self, subset_name, asset_ids, subset_counter, parent_item=None
    ):
        total = len(asset_ids)
        str_order_temp = "1%0{}d".format(len(str(total)))
        subset_color = self.merged_subset_colors[
            subset_counter % len(self.merged_subset_colors)
        ]
        inverse_order = total - subset_counter
        merge_group = Item()
        merge_group.update({
            "subset": "{} ({})".format(subset_name, len(asset_ids)),
            "isMerged": True,
            "childRow": 0,
            "subsetColor": subset_color,
            "assetIds": list(asset_ids),

            "icon": qtawesome.icon(
                "fa.circle",
                color="#{0:02x}{1:02x}{2:02x}".format(*subset_color)
            ),
            "order": "1{}".format(subset_name),
            "inverseOrder": str_order_temp % inverse_order
        })

        subset_counter += 1
        self.add_child(merge_group, parent_item)

        return merge_group

    def _fill_subset_items(
        self, asset_docs_by_id, subset_docs_by_id, last_versions_by_subset_id
    ):
        groups, subset_docs_without_group, subset_docs_by_group = (
            self.split_for_group(subset_docs_by_id.values())
        )

        group_item_by_name = {}
        for group_name, group_data in groups.items():
            group_item = Item()
            group_item.update({
                "subset": group_name,
                "isGroup": True,
                "childRow": 0
            })
            group_item.update(group_data)

            self.add_child(group_item)

            group_item_by_name[group_name] = {
                "item": group_item,
                "index": self.index(group_item.row(), 0)
            }

        subset_counter = 0
        for subset_name in sorted(subset_docs_without_group.keys()):
            subset_docs = subset_docs_without_group[subset_name]
            asset_ids = [subset_doc["parent"] for subset_doc in subset_docs]
            parent_item = None
            parent_index = None
            if len(subset_docs) > 1:
                parent_item = self.create_multiasset_group(
                    subset_name, asset_ids, subset_counter
                )
                parent_index = self.index(parent_item.row(), 0)
                subset_counter += 1

            for subset_doc in subset_docs:
                asset_id = subset_doc["parent"]

                data = copy.deepcopy(subset_doc)
                data["subset"] = subset_name
                data["asset"] = asset_docs_by_id[asset_id]["name"]

                last_version = last_versions_by_subset_id.get(
                    subset_doc["_id"]
                )
                data["last_version"] = last_version

                item = Item()
                item.update(data)
                self.add_child(item, parent_item)

                index = self.index(item.row(), 0, parent_index)
                self.set_version(index, last_version)

        for group_name, subset_docs_by_name in subset_docs_by_group.items():
            parent_item = group_item_by_name[group_name]["item"]
            parent_index = group_item_by_name[group_name]["index"]
            for subset_name in sorted(subset_docs_by_name.keys()):
                subset_docs = subset_docs_by_name[subset_name]
                asset_ids = [
                    subset_doc["parent"] for subset_doc in subset_docs
                ]
                if len(subset_docs) > 1:
                    _parent_item = self.create_multiasset_group(
                        subset_name, asset_ids, subset_counter, parent_item
                    )
                    _parent_index = self.index(
                        _parent_item.row(), 0, parent_index
                    )
                    subset_counter += 1
                else:
                    _parent_item = parent_item
                    _parent_index = parent_index

                for subset_doc in subset_docs:
                    asset_id = subset_doc["parent"]

                    data = copy.deepcopy(subset_doc)
                    data["subset"] = subset_name
                    data["asset"] = asset_docs_by_id[asset_id]["name"]

                    last_version = last_versions_by_subset_id.get(
                        subset_doc["_id"]
                    )
                    data["last_version"] = last_version

                    item = Item()
                    item.update(data)
                    self.add_child(item, _parent_item)

                    index = self.index(item.row(), 0, _parent_index)
                    self.set_version(index, last_version)

        self.endResetModel()
        self.refreshed.emit(True)


class FamiliesFilterProxyModel(loader_models.FamiliesFilterProxyModel):
    """Filters to specified families"""

    def __init__(self, *args, **kwargs):
        super(FamiliesFilterProxyModel, self).__init__(*args, **kwargs)

    def filterAcceptsRow(self, row=0, parent=QtCore.QModelIndex()):

        if not self._families:
            return False

        model = self.sourceModel()
        index = model.index(row, 0, parent=parent)

        # Ensure index is valid
        if not index.isValid() or index is None:
            return True

        # Get the node data and validate
        item = model.data(index, TreeModel.ItemRole)

        if item.get("isGroup"):
            return self.filter_accepts_group(index, model)

        families = item.get("families", [])

        filterable_families = set()
        for name in families:
            family_config = lib.get_family_cached_config(name)
            if not family_config.get("hideFilter"):
                filterable_families.add(name)

        if not filterable_families:
            return True

        # We want to keep the families which are not in the list
        return filterable_families.issubset(self._families)

    def sort(self, column, order):
        proxy = self.sourceModel()
        model = proxy.sourceModel()
        # We need to know the sorting direction for pinning groups on top
        if order == QtCore.Qt.AscendingOrder:
            self.setSortRole(model.SortAscendingRole)
        else:
            self.setSortRole(model.SortDescendingRole)

        super(FamiliesFilterProxyModel, self).sort(column, order)

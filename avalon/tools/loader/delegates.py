import time
from datetime import datetime
import logging

from ...vendor.Qt import QtWidgets, QtGui, QtCore
from ...vendor import Qt
from ..models import AssetModel

log = logging.getLogger(__name__)


def pretty_date(t, now=None, strftime="%b %d %Y %H:%M"):
    """Parse datetime to readable timestamp

    Within first ten seconds:
        - "just now",
    Within first minute ago:
        - "%S seconds ago"
    Within one hour ago:
        - "%M minutes ago".
    Within one day ago:
        - "%H:%M hours ago"
    Else:
        "%Y-%m-%d %H:%M:%S"

    """

    assert isinstance(t, datetime)
    if now is None:
        now = datetime.now()
    assert isinstance(now, datetime)
    diff = now - t

    second_diff = diff.seconds
    day_diff = diff.days

    # future (consider as just now)
    if day_diff < 0:
        return "just now"

    # history
    if day_diff == 0:
        if second_diff < 10:
            return "just now"
        if second_diff < 60:
            return str(second_diff) + " seconds ago"
        if second_diff < 120:
            return "a minute ago"
        if second_diff < 3600:
            return str(second_diff // 60) + " minutes ago"
        if second_diff < 86400:
            minutes = (second_diff % 3600) // 60
            hours = second_diff // 3600
            return "{0}:{1:02d} hours ago".format(hours, minutes)

    return t.strftime(strftime)


def pretty_timestamp(t, now=None):
    """Parse timestamp to user readable format

    >>> pretty_timestamp("20170614T151122Z", now="20170614T151123Z")
    'just now'

    >>> pretty_timestamp("20170614T151122Z", now="20170614T171222Z")
    '2:01 hours ago'

    Args:
        t (str): The time string to parse.
        now (str, optional)

    Returns:
        str: human readable "recent" date.

    """

    if now is not None:
        try:
            now = time.strptime(now, "%Y%m%dT%H%M%SZ")
            now = datetime.fromtimestamp(time.mktime(now))
        except ValueError as e:
            log.warning("Can't parse 'now' time format: {0} {1}".format(t, e))
            return None

    try:
        t = time.strptime(t, "%Y%m%dT%H%M%SZ")
    except ValueError as e:
        log.warning("Can't parse time format: {0} {1}".format(t, e))
        return None
    dt = datetime.fromtimestamp(time.mktime(t))

    # prettify
    return pretty_date(dt, now=now)


class PrettyTimeDelegate(QtWidgets.QStyledItemDelegate):
    """A delegate that displays a timestamp as a pretty date.

    This displays dates like `pretty_date`.

    """

    def displayText(self, value, locale):
        return pretty_timestamp(value)


class AssetDelegate(QtWidgets.QItemDelegate):
    bar_height = 3

    def sizeHint(self, option, index):
        result = super(AssetDelegate, self).sizeHint(option, index)
        height = result.height()
        result.setHeight(height + self.bar_height)

        return result

    def paint(self, painter, option, index):
        painter.save()

        item_rect = QtCore.QRect(option.rect)
        item_rect.setHeight(option.rect.height() - self.bar_height)

        subset_colors = index.data(AssetModel.subsetColorsRole)
        subset_colors_width = 0
        if subset_colors:
            subset_colors_width = option.rect.width()/len(subset_colors)

        subset_rects = []
        counter = 0
        for subset_c in subset_colors:
            new_color = None
            new_rect = None
            if subset_c:
                new_color = QtGui.QColor(*subset_c)

                new_rect = QtCore.QRect(
                    option.rect.left() + (counter * subset_colors_width),
                    option.rect.top() + (option.rect.height()-self.bar_height),
                    subset_colors_width,
                    self.bar_height
                )
            subset_rects.append((new_color, new_rect))
            counter += 1

        # Background
        bg_color = QtGui.QColor(60, 60, 60)
        if option.state & QtWidgets.QStyle.State_Selected:
            if len(subset_colors) == 0:
                item_rect.setTop(item_rect.top() + (self.bar_height / 2))
            if option.state & QtWidgets.QStyle.State_MouseOver:
                bg_color.setRgb(70, 70, 70)
        else:
            item_rect.setTop(item_rect.top() + (self.bar_height / 2))
            if option.state & QtWidgets.QStyle.State_MouseOver:
                bg_color.setAlpha(100)
            else:
                bg_color.setAlpha(0)

        # # -- When not needed to do a rounded corners (easier and without painter restore):
        # painter.fillRect(
        #     item_rect,
        #     QtGui.QBrush(bg_color)
        # )
        pen = painter.pen()
        pen.setStyle(QtCore.Qt.NoPen)
        pen.setWidth(0)
        painter.setPen(pen)
        painter.setBrush(QtGui.QBrush(bg_color))
        painter.drawRoundedRect(option.rect, 3, 3)

        if option.state & QtWidgets.QStyle.State_Selected:
            for color, subset_rect in subset_rects:
                if not color or not subset_rect:
                    continue
                painter.fillRect(subset_rect, QtGui.QBrush(color))

        painter.restore()
        painter.save()

        # Icon
        icon_index = index.model().index(
            index.row(), index.column(), index.parent()
        )
        # - Default icon_rect if not icon
        icon_rect = QtCore.QRect(
            item_rect.left(),
            item_rect.top(),
            # To make sure it's same size all the time
            option.rect.height() - self.bar_height,
            option.rect.height() - self.bar_height
        )
        icon = index.model().data(icon_index, QtCore.Qt.DecorationRole)

        if icon:
            margin = 0
            mode = QtGui.QIcon.Normal

            if not (option.state & QtWidgets.QStyle.State_Enabled):
                mode = QtGui.QIcon.Disabled
            elif option.state & QtWidgets.QStyle.State_Selected:
                mode = QtGui.QIcon.Selected

            if isinstance(icon, QtGui.QPixmap):
                icon = QtGui.QIcon(icon)
                option.decorationSize = icon.size() / icon.devicePixelRatio()

            elif isinstance(icon, QtGui.QColor):
                pixmap = QtGui.QPixmap(option.decorationSize)
                pixmap.fill(icon)
                icon = QtGui.QIcon(pixmap)

            elif isinstance(icon, QtGui.QImage):
                icon = QtGui.QIcon(QtGui.QPixmap.fromImage(icon))
                option.decorationSize = icon.size() / icon.devicePixelRatio()

            elif isinstance(icon, QtGui.QIcon):
                state = QtGui.QIcon.Off
                if option.state & QtWidgets.QStyle.State_Open:
                    state = QtGui.QIcon.On
                actualSize = option.icon.actualSize(
                    option.decorationSize, mode, state
                )
                option.decorationSize = QtCore.QSize(
                    min(option.decorationSize.width(), actualSize.width()),
                    min(option.decorationSize.height(), actualSize.height())
                )

            state = QtGui.QIcon.Off
            if option.state & QtWidgets.QStyle.State_Open:
                state = QtGui.QIcon.On

            icon.paint(
                painter, icon_rect,
                QtCore.Qt.AlignLeft , mode, state
            )

        # Text
        text_rect = QtCore.QRect(
            icon_rect.left() + icon_rect.width() + 2,
            item_rect.top(),
            item_rect.width(),
            item_rect.height()
        )

        painter.drawText(
            text_rect, QtCore.Qt.AlignVCenter,
            index.data(QtCore.Qt.DisplayRole)
        )

        painter.restore()
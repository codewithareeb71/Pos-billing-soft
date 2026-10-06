"""Users, roles and the permission matrix."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QTabWidget, QVBoxLayout, QWidget)

from ... import config
from ...core.exceptions import AppError
from .. import icons, widgets


class UserDialog(widgets.FormDialog):
    def __init__(self, ctx, parent=None, user: dict | None = None):
        super().__init__(parent, "Edit user" if user else "New user", "Save user")
        self.ctx = ctx
        self.user = user
        self.user_id = user["id"] if user else None
        self.setMinimumWidth(480)

        self.username = QLineEdit(user["username"] if user else "")
        self.username.setPlaceholderText("At least 3 characters")
        if user:
            self.username.setReadOnly(True)
        self.full_name = QLineEdit(user.get("full_name", "") if user else "")
        self.email = QLineEdit(user.get("email", "") if user else "")
        self.phone = QLineEdit(user.get("phone", "") if user else "")
        self.role = QComboBox()
        for role in ctx.auth.list_roles():
            self.role.addItem(role["name"], role["id"])
        if user:
            index = self.role.findData(user.get("role_id"))
            if index >= 0:
                self.role.setCurrentIndex(index)
        self.active = QCheckBox("Account is active")
        self.active.setChecked(bool(user.get("active", 1)) if user else True)

        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText(
            "Leave blank to keep the current password" if user
            else f"At least {config.MIN_PASSWORD_LENGTH} characters *")
        self.confirm = QLineEdit()
        self.confirm.setEchoMode(QLineEdit.Password)
        self.confirm.setPlaceholderText("Repeat the password")

        self.add_field("Username *" if not user else "Username", self.username)
        self.add_field("Full name", self.full_name)
        self.add_field("Role", self.role)
        self.add_field("Email", self.email)
        self.add_field("Phone", self.phone)
        self.add_field("Password" + ("*" if not user else ""), self.password)
        self.add_field("Confirm password", self.confirm)
        self.form.addRow("", self.active)

    def validate(self) -> str:
        if not self.user and len(self.username.text().strip()) < 3:
            return "Username must be at least 3 characters long."
        password = self.password.text()
        if not self.user or password:
            if len(password) < config.MIN_PASSWORD_LENGTH:
                return f"Password must be at least {config.MIN_PASSWORD_LENGTH} " \
                       "characters long."
            if password != self.confirm.text():
                return "The passwords do not match."
        return ""

    def accept(self) -> None:
        try:
            if self.user_id:
                self.ctx.auth.update_user(
                    self.user_id, self.full_name.text().strip(),
                    int(self.role.currentData()), self.active.isChecked(),
                    self.email.text().strip(), self.phone.text().strip(),
                    session=self.ctx.session)
                if self.password.text():
                    self.ctx.auth.set_password(self.user_id, self.password.text(),
                                               session=self.ctx.session)
            else:
                self.user_id = self.ctx.auth.create_user(
                    self.username.text().strip(), self.password.text(),
                    self.full_name.text().strip(), int(self.role.currentData()),
                    session=self.ctx.session, email=self.email.text().strip(),
                    phone=self.phone.text().strip())
        except AppError as exc:
            self.set_error(exc.message)
            return
        super().accept()


class RoleDialog(widgets.FormDialog):
    def __init__(self, ctx, parent=None):
        super().__init__(parent, "New role", "Create role")
        self.ctx = ctx
        self.role_id: int | None = None
        self.name = QLineEdit()
        self.name.setPlaceholderText("e.g. Supervisor")
        self.description = QLineEdit()
        self.copy_from = QComboBox()
        self.copy_from.addItem("No permissions", None)
        for role in ctx.auth.list_roles():
            self.copy_from.addItem(role["name"], role["id"])
        self.add_field("Role name *", self.name)
        self.add_field("Description", self.description)
        self.add_field("Copy permissions from", self.copy_from)

    def validate(self) -> str:
        if not self.name.text().strip():
            return "Role name is required."
        return ""

    def accept(self) -> None:
        try:
            self.role_id = self.ctx.auth.create_role(
                self.name.text(), self.description.text().strip(),
                copy_from=self.copy_from.currentData(), session=self.ctx.session)
        except AppError as exc:
            self.set_error(exc.message)
            return
        super().accept()


class UsersPage(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._boxes: dict[str, QCheckBox] = {}
        self._current_role: int | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        root.addWidget(widgets.PageHeader("Users & roles",
                                          "Accounts, roles and fine-grained "
                                          "permissions"))
        tabs = QTabWidget()
        tabs.addTab(self._build_users_tab(), "Users")
        tabs.addTab(self._build_roles_tab(), "Roles & permissions")
        root.addWidget(tabs, 1)

    # ------------------------------------------------------------ users tab
    def _build_users_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)
        columns = [
            widgets.Column("username", "Username", 150),
            widgets.Column("full_name", "Full name", 200),
            widgets.Column("role", "Role", 150),
            widgets.Column("email", "Email", 200),
            widgets.Column("last_login", "Last sign in", 170),
            widgets.Column("active", "Status", 110, "center",
                           lambda v: "Active" if v else "Disabled"),
        ]
        self.table, self.model = widgets.make_table(columns, [])
        self.table.doubleClicked.connect(lambda *_: self.edit_user())
        layout.addWidget(self.table, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        new = QPushButton("New user")
        new.setProperty("variant", "primary")
        new.setIcon(icons.icon("add", "primary", 16))
        new.clicked.connect(self.add_user)
        edit = QPushButton("Edit")
        edit.setIcon(icons.icon("edit", "primary", 16))
        edit.clicked.connect(self.edit_user)
        password = QPushButton("Reset password")
        password.setIcon(icons.icon("key", "primary", 16))
        password.clicked.connect(self.reset_password)
        toggle = QPushButton("Enable / disable")
        toggle.clicked.connect(self.toggle_user)
        for button in (new, edit, password, toggle):
            footer.addWidget(button)
        footer.addStretch(1)
        layout.addLayout(footer)
        layout.addWidget(widgets.hint(
            "Cashiers can sell, reprint receipts and process returns. Sensitive "
            "settings, reports and database restore stay with administrators."))
        return page

    # -------------------------------------------------------- permissions tab
    def _build_roles_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(QLabel("Role"))
        self.role_combo = QComboBox()
        self.role_combo.currentIndexChanged.connect(lambda *_: self._load_role())
        top.addWidget(self.role_combo, 1)
        if self.ctx.session and self.ctx.session.is_admin:
            new_role = QPushButton("New role")
            new_role.setIcon(icons.icon("add", "primary", 16))
            new_role.clicked.connect(self.add_role)
            top.addWidget(new_role)
        self.save_permissions = QPushButton("Save permissions")
        self.save_permissions.setProperty("variant", "primary")
        self.save_permissions.clicked.connect(self.save_role_permissions)
        top.addWidget(self.save_permissions)
        layout.addLayout(top)

        from PySide6.QtWidgets import QScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        self.permissions_layout = QGridLayout(container)
        self.permissions_layout.setContentsMargins(0, 0, 0, 0)
        self.permissions_layout.setSpacing(6)
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)
        layout.addWidget(widgets.hint(
            "Permissions are checked at runtime - they are never hard-coded in "
            "the interface."))
        return page

    # ------------------------------------------------------------------ data
    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        self.model.set_rows(self.ctx.auth.list_users())
        self.table.resizeColumnsToContents()
        current = self.role_combo.currentData()
        self.role_combo.blockSignals(True)
        self.role_combo.clear()
        for role in self.ctx.auth.list_roles():
            label = role["name"]
            if role["is_system"]:
                label += "  (built-in)"
            self.role_combo.addItem(label, role["id"])
        index = self.role_combo.findData(current)
        if index >= 0:
            self.role_combo.setCurrentIndex(index)
        self.role_combo.blockSignals(False)
        if self._current_role is None and self.role_combo.count():
            self._current_role = self.role_combo.currentData()
            self._load_role()
        elif self.role_combo.count():
            self._load_role()

    def _load_role(self) -> None:
        role_id = self.role_combo.currentData()
        if not role_id:
            return
        self._current_role = role_id
        granted = self.ctx.auth.role_permissions(role_id)
        permissions = self.ctx.auth.list_permissions()

        while self.permissions_layout.count():
            item = self.permissions_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._boxes = {}
        modules: dict[str, list[dict]] = {}
        for permission in permissions:
            modules.setdefault(permission["module"], []).append(permission)
        for column, (module, entries) in enumerate(sorted(modules.items())):
            box = QWidget()
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(8, 8, 8, 8)
            box_layout.setSpacing(4)
            title = QLabel(module)
            title.setStyleSheet(f"font-weight:700; color:{self._color()};")
            box_layout.addWidget(title)
            for permission in entries:
                check = QCheckBox(permission["description"])
                check.setChecked(permission["code"] in granted)
                check.setProperty("code", permission["code"])
                box_layout.addWidget(check)
                self._boxes[permission["code"]] = check
            self.permissions_layout.addWidget(box, 0, column)
        self.permissions_layout.addWidget(QWidget(), 0, len(modules))

    @staticmethod
    def _color() -> str:
        from .. import theme
        return theme.PRIMARY

    def save_role_permissions(self) -> None:
        role_id = self.role_combo.currentData()
        if not role_id:
            return
        granted = {code for code, box in self._boxes.items() if box.isChecked()}
        try:
            self.ctx.auth.set_role_permissions(role_id, granted, session=self.ctx.session)
        except AppError as exc:
            widgets.error_box(self, exc)
            return
        widgets.notify(self, "Permissions saved", "success")

    # -------------------------------------------------------------- actions
    def add_user(self) -> None:
        dialog = UserDialog(self.ctx, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()
            widgets.notify(self, "User created", "success")

    def edit_user(self) -> None:
        record = widgets.selected_row(self.table)
        if not record:
            widgets.notify(self, "Select a user first.", "warning")
            return
        dialog = UserDialog(self.ctx, self, record)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()
            widgets.notify(self, "User updated", "success")

    def reset_password(self) -> None:
        record = widgets.selected_row(self.table)
        if not record:
            widgets.notify(self, "Select a user first.", "warning")
            return
        dialog = widgets.FormDialog(self, f"Reset password - {record['username']}",
                                    "Set password")
        first = QLineEdit()
        first.setEchoMode(QLineEdit.Password)
        second = QLineEdit()
        second.setEchoMode(QLineEdit.Password)
        dialog.add_field("New password", first)
        dialog.add_field("Confirm password", second)

        def check() -> str:
            if len(first.text()) < config.MIN_PASSWORD_LENGTH:
                return f"Password must be at least {config.MIN_PASSWORD_LENGTH} " \
                       "characters long."
            if first.text() != second.text():
                return "The passwords do not match."
            return ""

        dialog.validate = check  # type: ignore[method-assign]
        original_accept = dialog.accept

        def accept() -> None:
            error = check()
            if error:
                dialog.set_error(error)
                return
            try:
                self.ctx.auth.set_password(record["id"], first.text(),
                                           session=self.ctx.session)
            except AppError as exc:
                dialog.set_error(exc.message)
                return
            original_accept()

        dialog.accept = accept  # type: ignore[method-assign]
        if dialog.exec() == QDialog.Accepted:
            widgets.notify(self, f"Password changed for {record['username']}",
                           "success")

    def toggle_user(self) -> None:
        record = widgets.selected_row(self.table)
        if not record:
            widgets.notify(self, "Select a user first.", "warning")
            return
        activate = not record["active"]
        if record["id"] == self.ctx.session.user_id and not activate:
            widgets.notify(self, "You cannot disable your own account.", "error")
            return
        if not widgets.confirm(self,
                               f"{'Enable' if activate else 'Disable'} "
                               f"'{record['username']}'?", "Please confirm"):
            return
        try:
            self.ctx.auth.update_user(record["id"], record["full_name"],
                                      record["role_id"], activate,
                                      record.get("email", ""), record.get("phone", ""),
                                      session=self.ctx.session)
        except AppError as exc:
            widgets.error_box(self, exc)
            return
        self.refresh()
        widgets.notify(self, "User updated", "success")

    def add_role(self) -> None:
        dialog = RoleDialog(self.ctx, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()
            for index in range(self.role_combo.count()):
                if self.role_combo.itemData(index) == dialog.role_id:
                    self.role_combo.setCurrentIndex(index)
            widgets.notify(self, "Role created", "success")


def create(ctx, parent=None) -> UsersPage:
    return UsersPage(ctx, parent)

  from ratatoskr_mcp_server.dbus import DBusProviderBase

class GNOMEShellDbus(DBusProviderBase):
    """ DBus Provider for GNOME Desktop """

    def __init__(self):
        super().__init__('org.gnome.Shell', '/org/gnome/Shell')

    def get_shell_version(self) -> str:
        """ Get the current Shell version """
        return str(self.get_property('org.gnome.Shell', 'ShellVersion'))


    

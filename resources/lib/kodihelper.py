import urllib

from viaplay import Viaplay

import xbmc
import xbmcvfs
import xbmcgui
import xbmcplugin
from xbmcaddon import Addon


class KodiHelper(object):
    def __init__(self, base_url=None, handle=None):
        addon = self.get_addon()
        self.base_url = base_url
        self.handle = handle
        self.addon_path = xbmc.translatePath(addon.getAddonInfo('path'))
        self.addon_profile = xbmc.translatePath(addon.getAddonInfo('profile'))
        self.addon_name = addon.getAddonInfo('id')
        self.addon_version = addon.getAddonInfo('version')
        self.language = addon.getLocalizedString
        self.logging_prefix = '[%s-%s]' % (self.addon_name, self.addon_version)
        if not xbmcvfs.exists(self.addon_profile):
            xbmcvfs.mkdir(self.addon_profile)
        self.vp = Viaplay(self.addon_profile, self.get_country_code(), True)

    def get_addon(self):
        """Returns a fresh addon instance."""
        return Addon()

    def get_setting(self, setting_id):
        addon = self.get_addon()
        setting = addon.getSetting(setting_id)
        if setting == 'true':
            return True
        elif setting == 'false':
            return False
        else:
            return setting

    def set_setting(self, key, value):
        return self.get_addon().setSetting(key, value)

    def log(self, string):
        msg = '%s: %s' % (self.logging_prefix, string)
        xbmc.log(msg=msg, level=xbmc.LOGDEBUG)

    def get_country_code(self):
        country_id = self.get_setting('country')
        if country_id == '0':
            country_code = 'se'
        elif country_id == '1':
            country_code = 'dk'
        elif country_id == '2':
            country_code = 'no'
        else:
            country_code = 'fi'

        self.log('viaplay.{0} selected.'.format(country_code))

        return country_code

    def dialog(self, dialog_type, heading, message=None, options=None, nolabel=None, yeslabel=None):
        dialog = xbmcgui.Dialog()
        if dialog_type == 'ok':
            dialog.ok(heading, message)
        elif dialog_type == 'yesno':
            return dialog.yesno(heading, message, nolabel=nolabel, yeslabel=yeslabel)
        elif dialog_type == 'select':
            ret = dialog.select(heading, options)
            if ret > -1:
                return ret
            else:
                return None

    def authorize(self):
        try:
            self.vp.validate_session()
            return True
        except self.vp.ViaplayError as error:
            if not error.value == 'PersistentLoginError' or error.value == 'MissingSessionCookieError':
                raise
            else:
                return self.device_registration()

    def device_registration(self):
        """Presents a dialog with information on how to activate the device.
        Attempts to authorize the device using the interval returned by the activation data."""
        activation_data = self.vp.get_activation_data()
        message = self.language(30039).format(activation_data['verificationUrl'], activation_data['userCode'])
        dialog = xbmcgui.DialogProgress()
        dialog.create(self.language(30040), message)
        secs = 0
        expires = activation_data['expires']
        increment = int(100 / expires)

        while secs < expires:
            try:
                self.vp.authorize_device(activation_data)
                return True
            except self.vp.ViaplayError as error:
                # raise all non-pending authorization errors
                if not error.value == 'DeviceAuthorizationPendingError':
                    raise
            secs += activation_data['interval']
            percent = increment * secs
            dialog.update(percent, message)
            xbmc.sleep(activation_data['interval'] * 1000)
            if dialog.iscanceled():
                return False

        return False

    def get_user_input(self, heading, hidden=False):
        keyboard = xbmc.Keyboard('', heading, hidden)
        keyboard.doModal()
        if keyboard.isConfirmed():
            query = keyboard.getText()
            self.log('User input string: %s' % query)
        else:
            query = None

        if query and len(query) > 0:
            return query
        else:
            return None

    def get_numeric_input(self, heading):
        dialog = xbmcgui.Dialog()
        numeric_input = dialog.numeric(0, heading)

        if len(numeric_input) > 0:
            return str(numeric_input)
        else:
            return None

    def add_item(self, title, params, items=False, folder=True, playable=False, info=None, art=None, content=False):
        addon = self.get_addon()
        listitem = xbmcgui.ListItem(label=title)

        if playable:
            listitem.setProperty('IsPlayable', 'true')
            folder = False
        if art:
            listitem.setArt(art)
        else:
            art = {
                'icon': addon.getAddonInfo('icon'),
                'fanart': addon.getAddonInfo('fanart')
            }
            listitem.setArt(art)
        if info:
            listitem.setInfo('video', info)
        if content:
            xbmcplugin.setContent(self.handle, content)

        recursive_url = self.base_url + '?' + urllib.urlencode(params)

        if items is False:
            xbmcplugin.addDirectoryItem(self.handle, recursive_url, listitem, folder)
        else:
            items.append((recursive_url, listitem, folder))
            return items

    def eod(self):
        """Tell Kodi that the end of the directory listing is reached."""
        xbmcplugin.endOfDirectory(self.handle)

    def play_video(self, input, streamtype, content, pincode=None):
        if streamtype == 'url':
            url = input
            guid = self.vp.get_products(input=url, method='url')['system']['guid']
        else:
            guid = input

        stream = self.vp.get_stream(guid, pincode=pincode)
        if stream:
            playitem = xbmcgui.ListItem(path=stream['mpd_url'])
            playitem.setProperty('inputstream.adaptive.license_type', 'com.widevine.alpha')
            playitem.setProperty('inputstream.adaptive.license_key', stream['license_url'] + '||' + self.vp.format_license_post_data(stream['release_pid'], 'B{SSM}') + '|JBlicense')
            if self.get_setting('subtitles'):
                playitem.setSubtitles(self.vp.download_subtitles(stream['subtitle_urls']))
            xbmcplugin.setResolvedUrl(self.handle, True, listitem=playitem)
        else:
            self.dialog(dialog_type='ok', heading=self.language(30005), message=self.language(30038))

    def get_as_bool(self, string):
        if string == 'true':
            return True
        else:
            return False

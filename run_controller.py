import sys
from os_ken.lib import hub
hub.patch(thread=False)

from os_ken import cfg, log, flags
from os_ken.base.app_manager import AppManager


def main():
    apps = sys.argv[1:] or ["controller.py"]
    cfg.CONF(args=[], project="os_ken")
    log.init_log()
    mgr = AppManager.get_instance()
    mgr.load_apps(apps)
    contexts = mgr.create_contexts()
    services = []
    services.extend(mgr.instantiate_apps(**contexts))
    try:
        hub.joinall(services)
    except KeyboardInterrupt:
        pass
    finally:
        mgr.close()


main()

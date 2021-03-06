import os
import subprocess as sp
from pathlib import Path

from charms.reactive import when, when_not, when_all, set_flag, hook, clear_flag, is_flag_set
from charmhelpers.core.host import ( adduser, add_group, symlink, chownr)
from charmhelpers.core.templating import render

from charmhelpers.core.hookenv import ( log, config, opened_ports, open_port, close_port, status_set, resource_get )

from charmhelpers.core.host import (
    chownr,
    service_restart,
    service_running,
    service_start,
)

from mcstatus import MinecraftServer

MINECRAFT_HOME = Path('/opt/minecraft')

@when_not('minecraft.installed')
def install_layer_minecraft_server():

    MINECRAFT_HOME.mkdir(mode=0o755, parents=True, exist_ok=True)
    
    add_group('minecraft')
    
    adduser(username='minecraft', primary_group='minecraft', home_dir=str(MINECRAFT_HOME))

    chownr(str(MINECRAFT_HOME), 'minecraft', 'minecraft', chowntopdir=True)
    
    render_eula()

    render_serverproperties()

    render_systemd()
    
    set_serverjar()
    
    sp.call(["systemctl", "daemon-reload"])
    
    set_flag('minecraft.installed')


@when('minecraft.installed')
@when('apt.installed.openjdk-8-jre-headless')
@when_not('minecraft.started' )
def start_restart_server():
    """
    Starts and restarts the server.
    """
    sinfo = os.stat(resource_get('server-jar'))

    sp = int(config('server-port'))
    open_port(sp)
    
    if sinfo.st_size > 0:
        
        if not service_running('minecraft'):
            
            log('Starting')

            status_set('maintenance', 'Starting...')

            service_start('minecraft')

            status_set('active', 'Ready.')

            set_flag('minecraft.started')
        
        else:

            log('Restarting.')

            status_set('maintenance', 'Restarting...')

            service_restart('minecraft')

            status_set('active', 'Ready.')

            set_flag('minecraft.started')
            
    else:
        
        status_set('blocked', 'Need server-jar resource.')



def render_eula():
    """ 
    Write eula.txt (This happens once at install)
    """
    with open("/opt/minecraft/eula.txt", "+w") as eula_file:
        print("eula=true", file=eula_file)

    chownr('/opt/minecraft/eula.txt','minecraft','minecraft')
    
    log("eula.txt rendered.")

@hook('update-status')
def statusupdate():

    status = None
    
    try:
        
        mcs = MinecraftServer("127.0.0.1", int(config('server-port')) )
        
        status = mcs.status()
        
        gamemode = config('gamemode')

        if service_running('minecraft'):
            
            status_set('active', "{} players online ({})".format(status.players.online,gamemode))
            
        else:
            
            status_set('waiting', 'Not running')
    
    except OSError:
        
        log("Unable to connect to get server status.")
        
    except Exception as e:
        
        log(e)
    



@when_all('config.changed', 'minecraft.started')
def config_changed_need_restart():
    """
    Runs when a config change to a running server has been triggered
    """        
    # Close any ports opened
    if is_flag_set('config.changed.server-port'):
        log("server-port changed. Trying to close old ports.")
        for p in opened_ports():
            close_port(int(p.split('/')[0]))
        
    render_serverproperties()
    
    start_restart_server()


def render_serverproperties():

    gm = config('gamemode')

    sp = int(config('server-port'))
    
    render(source='server.properties',
           target='/opt/minecraft/server.properties',
           owner='minecraft',
           group='minecraft',
           perms=0o755,
           context=config())
    
    log("server.properties rendered.")

    

def render_systemd():
    
    serverjar = resource_get('server-jar')

    render(source='minecraft.service',
           target='/etc/systemd/system/minecraft.service',
	   owner='root',
           perms=0o775,
	   context={
               'server_jar': serverjar,
           })

    log("systemd unitfile rendered.")


def set_serverjar():
    """ Create and update server jar """
    server_jar = resource_get('server-jar')

    symlink(server_jar,'/opt/minecraft/minecraft_server.jar')


    
@hook('upgrade-charm')
def upgrade_charm():
    """ Handle new server jar resource here """
    set_serverjar()

    clear_flag('minecraft.started')

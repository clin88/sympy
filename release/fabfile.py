from collections import defaultdict

from fabric.api import env, local, run, sudo, cd, hide, prefix
from fabric.context_managers import shell_env, prefix
from fabric.operations import put, get
from fabric.contrib.files import append, exists
env.use_ssh_config = True

def prepare():
    prepare_apt()
    checkout_cache()

def prepare_apt():
    sudo("apt-get -qq update")
    sudo("apt-get -y install git python3 make python-virtualenv zip python-dev")
    # Needed to build the docs
    sudo("apt-get -y install graphviz inkscape texlive texlive-xetex texlive-fonts-recommended texlive-latex-extra")

def remove_userspace():
    """
    Deletes (!) the SymPy changes. Use with great care.
    """
    run("rm -rf repos")

def checkout_cache():
    run("rm -rf sympy-cache.git")
    run("git clone --bare https://github.com/sympy/sympy.git sympy-cache.git")

def gitrepos(branch=None):
    if not branch:
        # Use the current branch (of this git repo, not the one in Vagrant)
        branch = local("git rev-parse --abbrev-ref HEAD", capture=True)
    run("mkdir -p repos")
    with cd("repos"):
        run("git clone --reference ../sympy-cache.git https://github.com/sympy/sympy.git")
        if branch != "master":
            with cd("sympy"):
                run("git checkout -t origin/%s" % branch)

def get_sympy_version():
    with cd("repos/sympy"):
        version = run('python -c "import sympy;print sympy.__version__"')
    assert '\n' not in version
    assert ' ' not in version
    assert '\t' not in version
    return version

def test():
    with cd("repos/sympy"):
        run("./setup.py test")

def release(branch=None):
    remove_userspace()
    gitrepos(branch)
    python2_tarball()
    python3_tarball()
    build_docs()
    copy_release_files()

def python2_tarball():
    with cd("repos/sympy"):
        run("git clean -dfx")
        run("./setup.py clean")
        run("./setup.py sdist")
        run("./setup.py bdist_wininst")
        run("mv dist/{2win32-orig} dist/{2win32}".format(**tarball_formatter))

def python3_tarball():
    with cd("repos/sympy"):
        run("bin/use2to3")
        with cd("py3k-sympy"):
            run("./setup.py clean")
            run("./setup.py sdist")
            # We have to have 3.2 and 3.3 tarballs to make things work in
            # pip. See https://groups.google.com/d/msg/sympy/JEwi4ohGB90/FfjVDxZIkSEJ.
            run("mv dist/{source-orig} dist/{3.2}".format(**tarball_formatter))
            run("cp dist/{3.2} dist/{3.3}".format(**tarball_formatter))
            # We didn't test this yet:
            #run("./setup.py bdist_wininst")

def build_docs():
    with cd("repos/sympy"):
        run("mkdir -p dist")
        run("virtualenv docs-virtualenv")
        run("source docs-virtualenv/bin/activate; pip install sphinx==1.1.3 numpy")
        with cd("doc"):
            run("make clean")
            run("source ../docs-virtualenv/bin/activate; make html-errors")
            with cd("_build"):
                run("mv html {html-nozip}".format(**tarball_formatter))
                run("zip -9lr {html} {html-nozip}".format(**tarball_formatter))
                run("cp {html} ../../dist/".format(**tarball_formatter))
            run("make clean")
            run("source ../docs-virtualenv/bin/activate; make latex")
            with cd("_build"):
                with cd("latex"):
                    run("make")
                    run("cp {pdf-orig} ../../../dist/{pdf}".format(**tarball_formatter))

def copy_release_files():
    with cd("repos/sympy"):
        run("mkdir -p /vagrant/release")
        run("cp dist/* /vagrant/release/")
        run("cp py3k-sympy/dist/* /vagrant/release/")

def show_files(file):
    """
    Show the contents of a tarball.

    The current options for file are

    2: The Python 2 tarball
    3: The Python 3 tarball
    2win: The Python 2 Windows installer (Not yet implemented!)
    3win: The Python 3 Windows installer (Not yet implemented!)
    html: The html docs zip
    """
    # TODO:
    # - Automatically check that Python 3 has the same files as Python 2
    # - List the files that are in git but not in the release
    # - List the files in the Windows installers
    if file == '2':
        local("tar tf release/{2}".format(**tarball_formatter))
    elif file == '3':
        py32 = "{3.2}".format(**tarball_formatter)
        py33 = "{3.3}".format(**tarball_formatter)
        assert md5(py32).split()[0] == md5(py33).split()[0]
        local("tar tf release/" + py32)
    elif file in {'2win', '3win'}:
        raise NotImplementedError("Windows installers")
    elif file == 'html':
        local("unzip -l release/{html}".format(**tarball_formatter))
    else:
        raise ValueError(file + " is not valid")

def md5(file='*'):
    out = local("md5sum release/" + file, capture=True)
    print out
    return out

def get_tarball_name(file):
    """
    Get the name of a tarball

    file should be one of

    source-orig: The original name of the source tarball
    2:           The Python 2 tarball (after renaming)
    3.2:         The Python 3.2 tarball (after renaming)
    3.3:         The Python 3.3 tarball (after renaming)
    2win32-orig: The original name of the Python 2 win32 installer
    2win32:      The name of the Python 2 win32 installer (after renaming)
    html:        The name of the html zip
    html-nozip:  The name of the html, without ".zip"
    pdf-orig:    The original name of the pdf file
    pdf:         The name of the pdf file (after renaming)
    """
    version = get_sympy_version()
    doctypename = defaultdict(str, {'html': 'zip', 'pdf': 'pdf'})
    winos = defaultdict(str, {'2win32': 'win32', '2win32-orig': 'linux-i686'})
    if file in {'source-orig', '2'}:
        name = 'sympy-{version}.tar.gz'
    elif file in {'3.2', '3.3'}:
        name = "sympy-{version}-py{pyversion}.tar.gz"
    elif file in {'2win32', '2win32-orig'}:
        name = "sympy-{version}.{wintype}.exe"
    elif file in {'html', 'pdf', 'html-nozip'}:
        name = "sympy-docs-{type}-{version}"
        if not file.endswith('nozip'):
            file += ".{extension}"
    elif file == 'pdf-orig':
        name = "sympy-{version}.pdf"
    else:
        raise ValueError(file + " is not a recognized argument")
    ret = name.format(version=version, pyversion=file, type=file,
        extension=doctypename[file], wintype=winos[file])
    print ret # REMOVE ME
    return ret

tarball_name_types = {
    'source-orig:',
    '2:',
    '3.2:',
    '3.3:',
    '2win32-orig:',
    '2win32:',
    'html:',
    'pdf-orig:',
    'pdf',
    }

tarball_formatter = {name: get_tarball_name(name) for name in tarball_name_types}

# ------------------------------------------------
# Vagrant related configuration

def vagrant():
    vc = _get_vagrant_config()
    # change from the default user to 'vagrant'
    env.user = vc['User']
    # connect to the port-forwarded ssh
    env.hosts = ['%s:%s' % (vc['HostName'], vc['Port'])]
    # use vagrant ssh key
    env.key_filename = vc['IdentityFile'].strip('"')
    # Forward the agent if specified:
    env.forward_agent = vc.get('ForwardAgent', 'no') == 'yes'

def _get_vagrant_config():
    """
    Parses vagrant configuration and returns it as dict of ssh parameters
    and their values
    """
    result = local('vagrant ssh-config', capture=True)
    conf = {}
    for line in iter(result.splitlines()):
        parts = line.split()
        conf[parts[0]] = ' '.join(parts[1:])
    return conf

def restart_network():
    """
    Do this if the VM won't connect to the internet.
    """
    run("sudo /etc/init.d/networking restart")

# ---------------------------------------
# Just a simple testing command:

def uname():
    run('uname -a')
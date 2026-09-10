"""Human-owned keyboard session; no model control tools."""
from .pilot_operator import KeyboardInput
import time


class KeyboardSession:
    """GUI thread owns input and transport. No background command sender.

    Tick frequently; a stalled GUI cannot keep transmitting cached input.
    STOP is best effort and not a motor-stop acknowledgement. The board's
    independent link-loss handling is still required.
    """

    def __init__(self, link, clock, *, advisory=None):
        self.link, self.clock, self.advisory = link, clock, advisory
        self.input = KeyboardInput()
        self.closed = False
        self.status = 'Connected; arming unverified'
        self.observation = None
        self.last_sample = None

    def press(self, key):
        if key == 'Escape':
            self.stop()
        else:
            self.input.press(key)

    def release(self, key):
        self.input.release(key)

    def tick(self, focused):
        if self.closed:
            return
        if not focused:
            self.stop()
            return
        try:
            def sample():
                self.last_sample = self.input.sample(self.clock())
                return self.last_sample
            self.link.step(sample)
            observation = self.link.take_telemetry()
            if observation is not None:
                self.observation = observation
                if self.advisory is not None:
                    self.advisory.offer(observation)
        except Exception:
            self.stop()
            self.status = 'Session ended: transport or input unavailable'

    def stop(self):
        if self.closed:
            return
        self.closed = True
        self.input.stop()
        sent = False
        try:
            sent = self.link.stop()
        except Exception:
            pass
        finally:
            try:
                self.link.close()
            except Exception:
                pass
            if self.advisory is not None:
                self.advisory.close()
        self.status = ('STOP sent; physical stop unverified' if sent else
                       'Session closed; STOP unconfirmed, link-loss failsafe required')


class KeyboardWindow:
    """Tk stays on the main thread; only read-only analysis uses a worker."""

    def __init__(self, root, connect, *, demo=False):
        import tkinter as tk
        self.root, self.connect_link, self.demo = root, connect, demo
        self.session = None
        self.worker_thread = None
        self.analysis_queue = None
        self.clock = lambda: time.monotonic_ns() // 1000
        root.title('LiteWing keyboard pilot' + (' — DEMO / NO RADIO' if demo else ''))
        tk.Label(root, text='GCS profile: 1 throttle / 2 roll / 3 pitch / 4 yaw / 5 mode\n'
                 '1000–2000; neutral 1500. Aircraft configuration must match.').pack(padx=20,pady=10)
        tk.Button(root, text='Start demo' if demo else 'Connect', command=self.connect).pack()
        self.controls = tk.Frame(root, width=600, height=160, takefocus=True,
                                 background='#203040', highlightthickness=2)
        self.controls.pack(padx=20,pady=10)
        self.controls.pack_propagate(False)
        tk.Label(self.controls, text='Click here for keyboard control\n'
                 'Arrows: pitch/roll   A/D: yaw   W/S: throttle\n'
                 'Hold Space at minimum throttle: request arming\n'
                 'Escape: STOP   Leaving this panel: end session',
                 background='#203040',foreground='white').pack(expand=True)
        self.controls.bind('<Button-1>', lambda event: self.controls.focus_set())
        self.controls.bind('<KeyPress>', self.key_press)
        self.controls.bind('<KeyRelease>', lambda event: self.session.release(event.keysym)
                           if self.session else None)
        self.controls.bind('<FocusOut>', lambda event: self.stop())
        root.bind('<Escape>', lambda event: self.stop())
        tk.Button(root, text='STOP / End session', command=self.stop).pack()
        self.status = tk.StringVar(value='Not connected; no commands sent')
        self.observed = tk.StringVar(value='Aircraft state unobserved')
        self.analysis = tk.StringVar(value='Advisory: no observation')
        self.commands = tk.StringVar(value='No input sample yet')
        for value in (self.status,self.commands,self.observed,self.analysis):
            tk.Label(root,textvariable=value,wraplength=620).pack(padx=15,pady=5)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(10,self.poll)

    def connect(self):
        import queue
        from threading import Thread
        from .advisory_handoff import AdvisoryWorker
        from .tools import run_preflight_tool
        if self.session is not None and not self.session.closed:
            return
        if self.worker_thread is not None and self.worker_thread.is_alive():
            self.status.set('Previous advisory worker is retiring; connect again shortly')
            return
        self.status.set('Connecting with neutral inputs; no automatic arming')
        try:
            link = self.connect_link()
        except Exception:
            self.status.set('Connection unavailable; no automatic retry')
            return
        session = None
        worker = None
        try:
            output = queue.Queue(maxsize=1)
            def analyze(runtime, observation):
                report = run_preflight_tool(runtime)
                try: output.put_nowait(str(report['overall']))
                except queue.Full: pass
            worker = AdvisoryWorker(analyze)
            session = KeyboardSession(link,self.clock,advisory=worker)
            self.session = session
            self.analysis_queue = output
            self.worker_thread = Thread(target=worker.run,name='litewing-advisory',daemon=True)
            self.worker_thread.start()
            self.observed.set('Aircraft state unobserved in this session')
            self.analysis.set('Advisory: no observation in this session')
            self.controls.focus_set()
        except Exception:
            if session is not None:
                session.stop()
                session.status = 'Session unavailable; startup failed, no automatic retry'
            else:
                try: link.stop()
                except Exception: pass
                try: link.close()
                except Exception: pass
                if worker is not None:
                    worker.close()
            self.status.set('Session unavailable; startup failed, no automatic retry')

    def key_press(self, event):
        if self.session:
            self.session.press(event.keysym)

    def stop(self):
        if self.session:
            self.session.stop()
            self.status.set(self.session.status)

    def poll(self):
        import queue
        if self.session:
            self.session.tick(self.root.focus_get() == self.controls)
            self.status.set(('DEMO / NO RADIO: ' if self.demo else '') + self.session.status)
            self.commands.set('Sampled channels (not output acknowledgement): %s' %
                              (self.session.last_sample,))
            item = self.session.observation
            if item is not None:
                age = max(0, (self.clock()-item.received_monotonic_us)/1_000_000)
                self.observed.set('Historical telemetry: armed=%s; age=%.1fs' %
                                  (item.snapshot.armed,age))
            if self.analysis_queue is not None:
                try: self.analysis.set('Historical advisory: ' + self.analysis_queue.get_nowait())
                except queue.Empty: pass
        self.root.after(10,self.poll)

    def close(self):
        self.stop()
        self.root.destroy()


def parse_options(argv=None):
    import argparse
    import ipaddress
    from pathlib import Path
    parser = argparse.ArgumentParser(description='LiteWing human keyboard pilot')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--demo',action='store_true',help='no radio or credentials')
    mode.add_argument('--live',action='store_true',help='connect only after clicking Connect')
    parser.add_argument('--bundle',type=Path)
    parser.add_argument('--host')
    options = parser.parse_args(argv)
    if options.demo and (options.bundle is not None or options.host is not None):
        parser.error('demo does not accept credentials or a peer')
    if options.live:
        if options.bundle is None or options.host is None:
            parser.error('live requires --bundle and --host')
        try: options.host = str(ipaddress.IPv4Address(options.host))
        except ValueError: parser.error('host must be an explicit IPv4 address')
    return options


def live_connector(bundle, host):
    """Return a deferred, neutral-only admission attempt. No network now."""
    def connect():
        import socket
        from .provisioning_bundle import load_pending
        from .pilot_udp import admit_udp
        _, blob = load_pending(bundle)
        sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        try:
            sock.connect((host,2390))
        except BaseException:
            sock.close()
            raise
        # admit_udp takes socket ownership even if admission fails.
        return admit_udp(sock,blob[8:40],
                         lambda: (1000,1500,1500,1500,1500,1500,1500,1500),
                         lambda: time.monotonic_ns()//1000)
    return connect


class DemoLink:
    """Input preview only. Never creates sockets or telemetry observations."""
    def step(self, sample): sample()
    def take_telemetry(self): return None
    def stop(self): return False
    def close(self): pass


def main(argv=None):
    options = parse_options(argv)
    try:
        import tkinter as tk
        root = tk.Tk()
    except Exception:
        print('Tk display unavailable; on Homebrew install python-tk@3.14')
        return 2
    window = KeyboardWindow(root, DemoLink if options.demo else
                            live_connector(options.bundle,options.host),demo=options.demo)
    try:
        root.mainloop()
    finally:
        window.stop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

import curses
from curses.textpad import rectangle, Textbox
import logging
import patcher
import os.path
#import oyaml
import yamloc
import subprocess
import tempfile
from datetime import datetime


logger = logging.getLogger(__name__)

def create_panel(parent, lines, cols, y, x, title=None, ):
    rectangle(parent, y, x, y+lines-1, x+cols-2)
    parent.noutrefresh()
    win = curses.newwin(lines-2, cols-3, y+1, x+1)
    if title:
        parent.addstr(y, x+3, f" {title} ")
    return win

class FPPerformer(object):

    VERSION = 0.1

    def __init__(self, pxr):
        self.pxr = pxr
        self.patch = 0

    def load_bank(self, bank_name=None):
        bank_name = bank_name or self.pxr.currentbank
        self.pxr.load_bank(bank_name)

        self.bank_file = os.path.join(self.pxr.bankdir, bank_name)
        with open(self.bank_file, 'r') as f:
            self.editor = yamloc.YAML_Editor(f)

    def main(self, stdscr):
        curses.halfdelay(5)
        self.stdscr = stdscr
        self.stdscr.refresh()

        self.refresh()

        self.run()

    def refresh(self):
        self.do_layout();
        self.select_patch(self.patch)

    def do_layout(self):
       
        lines, cols = self.stdscr.getmaxyx()

        split = int(cols / 3)
        right = cols - split

        self.stdscr.clear()
        self.stdscr.refresh()

        self.titlebar = create_panel(self.stdscr, 3, cols, 0, 0)
        self.titlebar.addstr(0, 2, f"FluidPatcher Performer v{self.VERSION}",
                curses.A_BOLD)
        self.titlebar.noutrefresh()

        
        self.patchlist = create_panel(self.stdscr, lines-3,
                split, 3, 0, "Patches")

        self.status = create_panel(self.stdscr, 5, right,
                lines-5, split, "Status")

        self.details = create_panel(self.stdscr, lines-8, right,
                3, split, "Details")

        curses.doupdate()

    def set_status(self, text, line=0, attrs=0):
        lines, cols = self.status.getmaxyx()
        self.status.addnstr(line, 0, text.ljust(cols), cols-1, attrs)
        self.status.refresh()

    @property
    def patch_name(self):
        return self.pxr.patch_name(self.patch)

    def select_patch(self, p):
        patches = self.pxr.patch_names()
        
        if p < 0 or p >= len(patches):
            self.set_status("Outside patch range")
            return

        self.patch = p
        warnings = pxr.select_patch(p)
        if warnings:
            self.set_status(" ".join(warnings), 0, curses.A_STANDOUT)
        else:
            self.set_status("Loaded " + patches[p], 0)

        lines, cols = self.patchlist.getmaxyx()

        h = int(lines/2) - 1

        for i in range(lines):
            m = p - h + i

            try:
                if m < 0: raise IndexError()
                text = patches[m]
            except IndexError:
                text = ""

            a = (curses.A_REVERSE|curses.A_BOLD) if m == p else 0
            self.patchlist.addnstr(i, 0, text.ljust(cols-1), cols-1, a)

        self.patchlist.refresh()

        patch_name = self.pxr.patch_name(self.patch)
        fragment = self.editor.get_fragment(f'0.0.0.patches.{patch_name}')
        self.details.clear()
        lines, cols = self.details.getmaxyx()
        
        text = fragment.text.split('\n')
        
        for i, line in enumerate(text[:lines]):
            self.details.addnstr(i, 0, line, cols)
        self.details.refresh()

    def edit_patch(self):
        patch_name = self.pxr.patch_name(self.patch)
        fragment = self.editor.get_fragment(f'0.0.0.patches.{patch_name}')
        with tempfile.TemporaryDirectory(prefix="fp_") as d:
            filename = os.path.join(d, f"{patch_name}.yaml")
            with open(filename, 'w') as f:
                f.write(fragment.text)
            subprocess.run(['vim', filename])
            with open(filename, 'r') as f:
                text = f.read()

        self.stdscr.keypad(True)

        self.editor.update_fragment(fragment, text)

        # dump and re-read
        try:
            self.pxr.save_bank(raw=self.editor.raw)
            self.set_status("Finished editing", 1)
        except:
            raise
            self.set_status("Error saving", 1)

    def handle_key(self, e):
        
        if e in ['KEY_DOWN', ' ', 'j']:
            return self.select_patch(self.patch+1)

        if e in ['KEY_UP', 'b', 'k']:
            return self.select_patch(self.patch-1)

        if e in ['KEY_HOME', 'g']:
            return self.select_patch(0)

        if e in ['KEY_END', 'G']:
            return self.select_patch(self.pxr.patches_count()-1)

        if e == 'KEY_PPAGE':
            return self.select_patch(max(0, self.patch-5))

        if e == 'KEY_NPAGE':
            return self.select_patch(min(self.pxr.patches_count()-1, self.patch+5))

        if e == 'KEY_RESIZE':
            return self.refresh()

        raise ValueError("Unknown key")


    def process_command(self, cmd):
        cmd = cmd.split()

        if cmd[0] in (":edit", ":e"):
            self.set_status("Entering edit mode")
            self.edit_patch()
            self.refresh()
            return

        if cmd[0] in (":load", ":l"):
            self.load_bank(cmd[1])
            self.refresh()
            return

        if cmd[0] in (":add", ":a"):
            self.append_patch(cmd[1])
            return

        if cmd[0] in (":quit", ":q"):
            self.stdscr.clear()
            self.stdscr.refresh()
            raise KeyboardInterrupt

        raise RuntimeError("Unknown command")

    def run(self):
        self.select_patch(0)
        buf = ""

        while True:
            _, cols = self.titlebar.getmaxyx()
            self.titlebar.addstr(0, cols-12, datetime.now().strftime(" %H:%M:%S "))
            self.titlebar.refresh()
            
            try:
                e = self.stdscr.getkey()
            except:
                continue
            
            try:
                self.handle_key(e)
                continue
            except ValueError:
                pass

            if e == 'KEY_BACKSPACE':
                buf = buf[:-1]

            elif e == '\x1b': # ESCAPE
                buf = ""

            elif e == 'kPRV5': # Break
                break

            elif e == '\n':
                try:
                    self.process_command(buf)
                except KeyboardInterrupt:
                    break
                except:
                    self.set_status(f"Error: {e}")
                buf = ""

            else:
                buf += e

            self.set_status(f"> {buf}", 2)


if __name__ == '__main__':
    import patcher
    import time
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="Performance mode for FluidPatcher")
    parser.add_argument('--config', '-c', default='SquishBox/squishboxconf.yaml', help='Config file')
    parser.add_argument('--bank', '-b', help='Bank to load')
    options = parser.parse_args()

    pxr = patcher.Patcher(options.config)

    performer = FPPerformer(pxr)
    performer.load_bank(options.bank)

    logger.info("Starting interface")
    time.sleep(0.5)

    curses.wrapper(performer.main)




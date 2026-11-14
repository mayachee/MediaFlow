"""Native file dialogs used by the local dashboard (one dialog per process)."""
import argparse
import json


def main():
    import tkinter as tk
    from tkinter import filedialog
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind', choices=['file', 'directory', 'newdirectory', 'savefile'])
    args = parser.parse_args()
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    try:
        if args.kind == 'file':
            path = filedialog.askopenfilename(parent=root)
        elif args.kind == 'savefile':
            path = filedialog.asksaveasfilename(parent=root)
        else:
            path = filedialog.askdirectory(parent=root, mustexist=args.kind == 'directory')
        print(json.dumps({'path': path}))
    finally:
        root.destroy()


if __name__ == '__main__':
    main()

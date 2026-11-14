"""Desktop control center for this workspace. Use --list for a headless catalog."""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

from tools.script_catalog import ROOT, ScriptJob, build_command, curated_tools, discover_scripts


def desktop(smoke=False):
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    from tkinter.scrolledtext import ScrolledText

    window = tk.Tk()
    if smoke:
        window.withdraw()
    window.title('Scripts Studio')
    window.geometry('1280x900')
    window.minsize(1000, 740)
    window.configure(background='#eef2f7')
    style = ttk.Style()
    style.theme_use('clam')
    style.configure('.', font=('Segoe UI', 10))
    style.configure('TFrame', background='white')
    style.configure('TLabel', background='white', foreground='#17243c')
    style.configure('Title.TLabel', font=('Segoe UI', 21, 'bold'))
    style.configure('Muted.TLabel', foreground='#64748b')
    style.configure('Section.TLabel', font=('Segoe UI', 11, 'bold'))
    style.configure('TButton', padding=(12, 8), background='#f1f5f9', foreground='#24334d', borderwidth=1)
    style.map('TButton', background=[('active', '#e2e8f0')])
    style.configure('Accent.TButton', background='#2563eb', foreground='white', font=('Segoe UI', 10, 'bold'))
    style.map('Accent.TButton', background=[('disabled', '#cbd5e1'), ('active', '#1d4ed8')],
              foreground=[('disabled', '#64748b'), ('active', 'white')])
    style.configure('TEntry', padding=7, fieldbackground='white', bordercolor='#cbd5e1')
    style.configure('TCombobox', padding=6, fieldbackground='white')
    style.configure('TCheckbutton', background='white', padding=(0, 5))
    style.configure('TNotebook', background='white', borderwidth=0, tabmargins=(0, 0, 0, 8))
    style.configure('TNotebook.Tab', padding=(16, 9), background='#e8eef7', foreground='#475569')
    style.map('TNotebook.Tab', background=[('selected', 'white')], foreground=[('selected', '#1d4ed8')])
    style.configure('Treeview', rowheight=30, background='white', fieldbackground='white', foreground='#334155', borderwidth=0)
    style.map('Treeview', background=[('selected', '#dbeafe')], foreground=[('selected', '#1e40af')])
    style.configure('Treeview.Heading', background='#edf2f9', padding=8, font=('Segoe UI', 10, 'bold'))
    style.configure('Side.TFrame', background='#14213a')
    style.configure('Side.TLabel', background='#14213a', foreground='#e2e8f0')
    style.configure('SideMuted.TLabel', background='#14213a', foreground='#a3b4cf')
    style.configure('Nav.Treeview', background='#14213a', fieldbackground='#14213a', foreground='#e2e8f0', rowheight=34)
    style.map('Nav.Treeview', background=[('selected', '#2563eb')], foreground=[('selected', 'white')])
    for name, color, background in [('Idle', '#1d4ed8', '#eff6ff'), ('Running', '#92400e', '#fef3c7'),
                                     ('Success', '#047857', '#d1fae5'), ('Failed', '#b91c1c', '#fee2e2')]:
        style.configure(f'{name}.TLabel', foreground=color, background=background, padding=(10, 5))
    events = queue.Queue()
    state = {'tool': None, 'job': None, 'busy': False, 'saved': {}, 'last_folder': ROOT / 'runs', 'cleaner_open': False}
    variables = {}
    guided, scripts = curated_tools(), discover_scripts()
    catalog = {tool['id']: tool for tool in guided + scripts}

    def open_folder(path):
        path = Path(path)
        if not path.is_dir():
            messagebox.showinfo('Folder not created yet', str(path), parent=window)
            return
        if os.name == 'nt':
            os.startfile(str(path))
        else:
            subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', str(path)])

    def show_file(path):
        try:
            content = Path(path).read_text(encoding='utf-8', errors='replace')
        except OSError as error:
            messagebox.showerror('Cannot read file', str(error), parent=window)
            return
        viewer = tk.Toplevel(window)
        viewer.title(str(path))
        viewer.geometry('950x650')
        text = ScrolledText(viewer, wrap='word', font=('Consolas', 10))
        text.pack(fill='both', expand=True)
        text.insert('end', content)
        text.config(state='disabled')

    def history():
        dialog = tk.Toplevel(window)
        dialog.title('Recent jobs')
        dialog.geometry('900x450')
        tree = ttk.Treeview(dialog, columns=('status', 'command'), show='tree headings')
        tree.heading('#0', text='Job')
        tree.heading('status', text='Status')
        tree.heading('command', text='Program')
        tree.column('status', width=100, stretch=False)
        tree.pack(fill='both', expand=True, padx=10, pady=10)
        entries = {}
        for path in sorted((ROOT / 'runs/script-manager').glob('*/job.json'), reverse=True)[:100]:
            try:
                document = json.loads(path.read_text(encoding='utf-8'))
                entries[str(path)] = path.parent
                tree.insert('', 'end', iid=str(path), text=path.parent.name,
                            values=(document['status'], subprocess.list2cmdline(document['command'])))
            except (OSError, ValueError, KeyError):
                continue
        def chosen(log=False):
            selection = tree.selection()
            if selection:
                folder = entries[selection[0]]
                show_file(folder / 'output.log') if log else open_folder(folder)
        row = ttk.Frame(dialog)
        row.pack(pady=(0, 10))
        ttk.Button(row, text='Read log', command=lambda: chosen(True)).pack(side='left', padx=5)
        ttk.Button(row, text='Open job folder', command=chosen).pack(side='left', padx=5)

    def cleaner_dialog():
        if state['busy']:
            messagebox.showinfo('A job is running', 'Finish or stop the current job before cleaning.', parent=window)
            return
        if state['cleaner_open']:
            return
        from tools.cleaner_ui import open_cleaner
        state['cleaner_open'] = True
        run_button.config(state='disabled')
        def closed():
            state['cleaner_open'] = False
            run_button.config(state='normal' if state['tool'] and state['tool']['runnable'] else 'disabled')
        open_cleaner(window, on_close=closed)

    top = ttk.Frame(window, padding=(22, 16))
    top.pack(fill='x', padx=14, pady=(14, 12))
    branding = ttk.Frame(top)
    branding.pack(side='left')
    ttk.Label(branding, text='Scripts Studio', style='Title.TLabel').pack(anchor='w')
    ttk.Label(branding, text='Your music, video and production workspace', style='Muted.TLabel').pack(anchor='w', pady=(3, 0))
    for label, callback in [('Help', lambda: show_file(ROOT / 'docs/SCRIPT_MANAGER.md')),
                            ('Recent jobs', history), ('Open results', lambda: open_folder(ROOT / 'runs')),
                            ('Cleaner', cleaner_dialog)]:
        ttk.Button(top, text=label, command=callback).pack(side='right', padx=4)
    interpreter = tk.StringVar(value=sys.executable)
    def choose_python():
        path = filedialog.askopenfilename(parent=window, title='Choose Python executable')
        if path:
            interpreter.set(path)
    split = ttk.Panedwindow(window, orient='horizontal')
    split.pack(fill='both', expand=True, padx=14, pady=(0, 14))
    left, right = ttk.Frame(split, style='Side.TFrame', padding=14), ttk.Frame(split, padding=18)
    split.add(left, weight=1)
    split.add(right, weight=3)
    search = tk.StringVar()
    ttk.Label(left, text='WORKSPACE TOOLS', style='Side.TLabel', font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=(4, 2))
    ttk.Label(left, text=f'{len(guided)} guided tools  |  {len(scripts)} scripts', style='SideMuted.TLabel').pack(anchor='w', pady=(0, 10))
    search_entry = ttk.Entry(left, textvariable=search)
    search_entry.pack(fill='x', pady=(0, 12))
    navigation = ttk.Notebook(left)
    navigation.pack(fill='both', expand=True)
    trees = []
    for title in ['Guided tools', 'All scripts']:
        frame = ttk.Frame(navigation)
        navigation.add(frame, text=title)
        tree = ttk.Treeview(frame, show='tree', selectmode='browse', style='Nav.Treeview')
        tree.tag_configure('group', foreground='#93c5fd', font=('Segoe UI', 9, 'bold'))
        scroll = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        tree.pack(fill='both', expand=True)
        trees.append(tree)
    title = tk.StringVar(value='Choose a tool')
    description = tk.StringVar()
    category_label = ttk.Label(right, text='CHOOSE A WORKFLOW', style='Muted.TLabel')
    category_label.pack(anchor='w', pady=(0, 5))
    ttk.Label(right, textvariable=title, font=('Segoe UI', 19, 'bold')).pack(anchor='w')
    description_label = ttk.Label(right, textvariable=description, wraplength=700, justify='left', style='Muted.TLabel')
    description_label.pack(fill='x', pady=(8, 14))
    right.bind('<Configure>', lambda event: description_label.configure(wraplength=max(300, event.width - 40)))
    body = ttk.Panedwindow(right, orient='vertical')
    body.pack(fill='both', expand=True)
    input_tabs, output_area = ttk.Notebook(body), ttk.Frame(body, padding=(0, 10, 0, 0))
    body.add(input_tabs, weight=3)
    body.add(output_area, weight=2)
    input_area, advanced_area = ttk.Frame(input_tabs), ttk.Frame(input_tabs, padding=12)
    input_tabs.add(input_area, text='Inputs')
    input_tabs.add(advanced_area, text='Advanced')
    canvas = tk.Canvas(input_area, highlightthickness=0, height=300, background='white')
    bar = ttk.Scrollbar(input_area, orient='vertical', command=canvas.yview)
    canvas.configure(yscrollcommand=bar.set)
    bar.pack(side='right', fill='y')
    canvas.pack(fill='both', expand=True)
    form = ttk.Frame(canvas, padding=8)
    form.columnconfigure(1, weight=1)
    canvas_item = canvas.create_window(0, 0, window=form, anchor='nw')
    form.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind('<Configure>', lambda event: canvas.itemconfigure(canvas_item, width=event.width))
    def scroll_inputs(event):
        if str(event.widget).startswith(str(input_area)) and event.widget.winfo_class() != 'TCombobox':
            canvas.yview_scroll(-int(event.delta / 120), 'units')
    window.bind('<MouseWheel>', scroll_inputs)
    ttk.Label(advanced_area, text='Python environment', style='Section.TLabel').pack(anchor='w')
    interpreter_row = ttk.Frame(advanced_area)
    interpreter_row.pack(fill='x', pady=(8, 14))
    ttk.Entry(interpreter_row, textvariable=interpreter).pack(side='left', fill='x', expand=True, padx=(0, 8))
    ttk.Button(interpreter_row, text='Browse', command=choose_python).pack(side='left')
    ttk.Label(advanced_area, text='Extra arguments', style='Section.TLabel').pack(anchor='w')
    ttk.Label(advanced_area, text='One argument per line; paths need no quotes.', style='Muted.TLabel').pack(anchor='w', pady=(4, 6))
    advanced = ScrolledText(advanced_area, height=3, wrap='none', font=('Consolas', 10), relief='flat', background='#f1f5f9')
    advanced.pack(fill='x', pady=4)
    console = tk.BooleanVar(value=False)
    ttk.Checkbutton(advanced_area, text='Open an interactive console (for scripts that ask questions)', variable=console).pack(anchor='w', pady=6)
    command_display = tk.StringVar(value='Use Preview command to check inputs before starting.')
    ttk.Label(advanced_area, textvariable=command_display, wraplength=700, justify='left', style='Muted.TLabel').pack(fill='x', pady=5)
    actions = ttk.Frame(right, padding=(0, 12, 0, 0))
    actions.pack(fill='x', side='bottom')
    status = tk.StringVar(value='Ready')
    activity_header = ttk.Frame(output_area)
    activity_header.pack(fill='x')
    ttk.Label(activity_header, text='Activity', style='Section.TLabel').pack(side='left')
    badge = ttk.Label(activity_header, text='Ready', style='Idle.TLabel')
    badge.pack(side='left', padx=12)
    elapsed = tk.StringVar(value='')
    ttk.Label(activity_header, textvariable=elapsed, style='Muted.TLabel').pack(side='right')
    progress = ttk.Progressbar(output_area, mode='indeterminate')
    progress.pack(fill='x', pady=(10, 8))
    ttk.Label(output_area, textvariable=status, wraplength=700, style='Muted.TLabel').pack(fill='x')
    logs = ScrolledText(output_area, height=9, state='disabled', font=('Consolas', 10),
                        background='#111c30', foreground='#dbe7fb', insertbackground='white', relief='flat', padx=12, pady=10)
    logs.pack(fill='both', expand=True, pady=(10, 0))

    def selected_command():
        tool = state['tool']
        if tool is None:
            raise ValueError('Choose a tool first.')
        values = {key: variable.get() for key, variable in variables.items()}
        extra = [line.strip() for line in advanced.get('1.0', 'end').splitlines() if line.strip()]
        return build_command(tool, values, extra, interpreter.get().strip())

    def preview():
        try:
            command, cwd = selected_command()
            command_display.set(f'Working folder: {cwd}\n{subprocess.list2cmdline(command)}')
            input_tabs.select(advanced_area)
        except (OSError, ValueError) as error:
            messagebox.showerror('Check your inputs', str(error), parent=window)

    def worker(job):
        try:
            result = job.run(lambda line: events.put(('log', line)))
            events.put(('done', result))
        except Exception as error:
            events.put(('done', {'status': 'failed', 'error': str(error)}))

    def start():
        if state['busy'] or state['cleaner_open']:
            return
        try:
            command, cwd = selected_command()
        except (OSError, ValueError) as error:
            messagebox.showerror('Check your inputs', str(error), parent=window)
            return
        job = ScriptJob(command, cwd, console=console.get())
        state.update(job=job, busy=True, last_folder=job.folder, started=time.monotonic())
        progress.start(12)
        badge.configure(text='Running', style='Running.TLabel')
        run_button.config(state='disabled')
        cancel_button.config(state='normal')
        status.set('Running: ' + state['tool']['title'])
        command_display.set(f'Working folder: {cwd}\n{subprocess.list2cmdline(command)}')
        logs.config(state='normal')
        logs.delete('1.0', 'end')
        logs.config(state='disabled')
        threading.Thread(target=worker, args=(job,), daemon=True).start()

    def cancel():
        if state['busy']:
            cancel_button.config(state='disabled')
            status.set('Stopping this job and its child processes...')
            threading.Thread(target=state['job'].cancel, daemon=True).start()

    def source():
        if state['tool'] and state['tool']['script']:
            show_file(ROOT / state['tool']['script'])

    for label, callback in [('Preview', preview), ('Source', source),
                            ('Job folder', lambda: open_folder(state['last_folder']))]:
        ttk.Button(actions, text=label, command=callback).pack(side='left', padx=(0, 5))
    run_button = ttk.Button(actions, text='Run tool', command=start, state='disabled', style='Accent.TButton')
    run_button.pack(side='right', padx=(8, 0))
    cancel_button = ttk.Button(actions, text='Stop', command=cancel, state='disabled')
    cancel_button.pack(side='right')

    def choose(event):
        tree = event.widget
        selection = tree.selection()
        if not selection or selection[0] not in catalog:
            return
        if state['tool']:
            state['saved'][state['tool']['id']] = ({key: variable.get() for key, variable in variables.items()},
                                                  advanced.get('1.0', 'end-1c'), console.get())
        tool = catalog[selection[0]]
        state['tool'] = tool
        title.set(tool['title'])
        category_label.configure(text=tool['category'].upper())
        description.set(tool['description'])
        for child in form.winfo_children():
            child.destroy()
        variables.clear()
        saved, extra, in_console = state['saved'].get(tool['id'], ({}, '', not tool['guided']))
        advanced.delete('1.0', 'end')
        advanced.insert('1.0', extra)
        console.set(in_console)
        for row, item in enumerate(tool['fields']):
            row *= 2
            key, kind = item['key'], item['kind']
            variable = tk.BooleanVar(value=saved.get(key, item['default'] or False)) if kind == 'bool' else tk.StringVar(value=saved.get(key, item['default']))
            variables[key] = variable
            if kind == 'bool':
                ttk.Checkbutton(form, text=item['label'], variable=variable).grid(row=row, column=0, columnspan=3, sticky='w', pady=5)
                continue
            ttk.Label(form, text=item['label'] + (' *' if item['required'] else '')).grid(row=row, column=0, columnspan=3, sticky='w', pady=(8, 4))
            widget = ttk.Combobox(form, textvariable=variable, values=item['choices'], state='readonly') if kind == 'choice' else ttk.Entry(form, textvariable=variable)
            widget.grid(row=row + 1, column=0, columnspan=2, sticky='ew', pady=(0, 6))
            if kind in {'file', 'directory', 'savefile', 'newdirectory'}:
                def browse(v=variable, k=kind):
                    if k == 'file':
                        path = filedialog.askopenfilename(parent=window)
                    elif k == 'savefile':
                        path = filedialog.asksaveasfilename(parent=window, defaultextension='.json')
                    else:
                        path = filedialog.askdirectory(parent=window, mustexist=k == 'directory')
                    if path:
                        v.set(path)
                ttk.Button(form, text='Browse', command=browse).grid(row=row + 1, column=2, padx=(8, 0), pady=(0, 6))
        if not tool['fields']:
            ttk.Label(form, text='No guided inputs. Use extra arguments below if the script needs them.').grid(sticky='w')
        canvas.yview_moveto(0)
        command_display.set('Use Preview command to check inputs before starting.')
        run_button.config(state='normal' if tool['runnable'] and not state['busy'] and not state['cleaner_open'] else 'disabled')

    def populate(*args):
        query = search.get().casefold().strip()
        for tree, entries in zip(trees, [guided, scripts]):
            tree.delete(*tree.get_children())
            groups = {}
            for tool in entries:
                if query and query not in (tool['title'] + ' ' + tool['description'] + ' ' + (tool['script'] or '')).casefold():
                    continue
                category = tool['category']
                if category not in groups:
                    groups[category] = tree.insert('', 'end', text=category.upper(), open=True, tags=('group',))
                tree.insert(groups[category], 'end', iid=tool['id'], text=tool['title'])

    def poll():
        if state['busy']:
            seconds = int(time.monotonic() - state['started'])
            elapsed.set(f'{seconds // 60:02d}:{seconds % 60:02d} elapsed')
        for _ in range(200):
            try:
                kind, value = events.get_nowait()
            except queue.Empty:
                break
            if kind == 'log':
                logs.config(state='normal')
                logs.insert('end', value)
                if int(logs.index('end-1c').split('.')[0]) > 2500:
                    logs.delete('1.0', '500.0')
                logs.see('end')
                logs.config(state='disabled')
            else:
                state['busy'] = False
                progress.stop()
                badge.configure(text=value['status'].capitalize(), style='Success.TLabel' if value['status'] == 'completed' else 'Failed.TLabel' if value['status'] == 'failed' else 'Idle.TLabel')
                cancel_button.config(state='disabled')
                run_button.config(state='normal' if state['tool'] and state['tool']['runnable'] and not state['cleaner_open'] else 'disabled')
                status.set(f"Job {value['status']}. Log: {state['last_folder'] / 'output.log'}")
                if value.get('error'):
                    messagebox.showerror('Job failed', value['error'], parent=window)
        window.after(100, poll)

    def close():
        if state['cleaner_open']:
            messagebox.showinfo('Cleaner is open', 'Close the cleaner window before closing Studio.', parent=window)
            return
        if state['busy']:
            messagebox.showinfo('A job is running', 'Use Stop job and wait for it to stop before closing.', parent=window)
        else:
            window.destroy()

    for tree in trees:
        tree.bind('<<TreeviewSelect>>', choose)
    search.trace_add('write', populate)
    populate()
    trees[0].selection_set('video')
    window.bind('<Control-f>', lambda event: search_entry.focus_set())
    window.bind('<Control-Return>', lambda event: start())
    window.protocol('WM_DELETE_WINDOW', close)
    if smoke:
        import tempfile
        from tools.cleaner_ui import open_cleaner
        window.update_idletasks()
        for tool in guided:
            trees[0].selection_set(tool['id'])
            choose(type('Selection', (), {'widget': trees[0]})())
            window.update_idletasks()
            assert set(variables) == {item['key'] for item in tool['fields']}
        search.set('autocrop')
        assert any(trees[0].get_children(group) for group in trees[0].get_children())
        search.set('')
        with tempfile.TemporaryDirectory() as fixture:
            cleaner_window = open_cleaner(window, root=fixture, hidden=True)
            window.update_idletasks()
            cleaner_window.destroy()
        print(json.dumps({'status': 'passed', 'forms': len(guided), 'cleaner_window': 'created', 'search': 'passed'}))
        window.destroy()
        return
    window.after(100, poll)
    window.mainloop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', action='store_true', help='Print available tools and scripts without opening a window')
    parser.add_argument('--ui-smoke', action='store_true', help='Build all forms and the cleaner in hidden windows without executing tools')
    parser.add_argument('--desktop', action='store_true', help='Open the earlier native desktop interface')
    parser.add_argument('--no-browser', action='store_true', help='Start the local dashboard without opening a browser')
    parser.add_argument('--port', type=int, default=0, help='Local dashboard port; default chooses a free port')
    args = parser.parse_args()
    if args.list:
        print(json.dumps({'guided': curated_tools(), 'scripts': discover_scripts()}, indent=2))
    elif args.desktop or args.ui_smoke:
        desktop(smoke=args.ui_smoke)
    else:
        from studio_server import serve
        serve(port=args.port, open_browser=not args.no_browser)


if __name__ == '__main__':
    main()

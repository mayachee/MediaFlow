"""Desktop cleanup preview and restorable Studio Trash."""
from pathlib import Path
import queue
import threading

from tools.workspace_cleaner import ROOT, WorkspaceCleaner, size_label


def open_cleaner(parent, on_close=lambda: None, root=ROOT, hidden=False):
    import tkinter as tk
    from tkinter import messagebox, ttk

    cleaner = WorkspaceCleaner(root)
    window = tk.Toplevel(parent)
    if hidden:
        window.withdraw()
    window.title('Workspace cleaner | Scripts Studio')
    window.geometry('1040x690')
    window.minsize(850, 580)
    window.transient(parent)
    if not hidden:
        window.grab_set()
    panel = ttk.Frame(window, padding=20)
    panel.pack(fill='both', expand=True)
    ttk.Label(panel, text='Workspace cleaner', style='Title.TLabel').pack(anchor='w')
    ttk.Label(panel, text='Review generated files, move them to Studio Trash, and restore them when needed.',
              style='Muted.TLabel').pack(anchor='w', pady=(5, 16))
    tabs = ttk.Notebook(panel)
    tabs.pack(fill='both', expand=True)
    review, trash = ttk.Frame(tabs, padding=14), ttk.Frame(tabs, padding=14)
    tabs.add(review, text='  Cleanup preview  ')
    tabs.add(trash, text='  Studio Trash  ')
    options = ttk.Frame(review)
    options.pack(fill='x', pady=(0, 12))
    caches, logs = tk.BooleanVar(value=True), tk.BooleanVar(value=True)
    ttk.Checkbutton(options, text='Python caches', variable=caches).pack(side='left')
    ttk.Checkbutton(options, text='Completed job logs', variable=logs).pack(side='left', padx=16)
    ttk.Label(options, text='Older than (days)').pack(side='left', padx=(12, 6))
    days = tk.StringVar(value='7')
    ttk.Spinbox(options, from_=0, to=3650, textvariable=days, width=6).pack(side='left')
    tables = []
    for frame in [review, trash]:
        box = ttk.Frame(frame)
        box.pack(fill='both', expand=True)
        tree = ttk.Treeview(box, columns=('type', 'size', 'path'), show='headings', selectmode='extended')
        for column, title, width in [('type', 'Type', 150), ('size', 'Size', 100), ('path', 'Folder', 600)]:
            tree.heading(column, text=title)
            tree.column(column, width=width, stretch=column == 'path')
        scroll = ttk.Scrollbar(box, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        tree.pack(fill='both', expand=True)
        tables.append(tree)
    preview_tree, trash_tree = tables
    summary = tk.StringVar(value='Choose categories and click Scan. No files have been changed.')
    ttk.Label(review, textvariable=summary, style='Muted.TLabel', wraplength=900).pack(anchor='w', pady=12)
    ttk.Label(review, text='Inputs, media, clip libraries, credentials, AI models, environments, and vendor tools are excluded.',
              style='Muted.TLabel', wraplength=900).pack(anchor='w', pady=(0, 12))
    review_actions = ttk.Frame(review)
    review_actions.pack(fill='x')
    trash_summary = tk.StringVar(value='Trash is loaded when you scan or refresh.')
    ttk.Label(trash, textvariable=trash_summary, style='Muted.TLabel').pack(anchor='w', pady=12)
    ttk.Label(trash, text='Moving to Trash is reversible. Disk space is freed only when you permanently empty selected batches.',
              style='Muted.TLabel', wraplength=900).pack(anchor='w', pady=(0, 12))
    trash_actions = ttk.Frame(trash)
    trash_actions.pack(fill='x')
    status = tk.StringVar(value='Ready')
    ttk.Label(panel, textvariable=status, style='Muted.TLabel').pack(anchor='w', pady=(12, 0))
    events = queue.Queue()
    state = dict(busy=False, closed=False, items=[], settings=dict(days=7, caches=True, logs=True))
    buttons = []

    def fill_trash(batches):
        trash_tree.delete(*trash_tree.get_children())
        for item in batches:
            document = item['document']
            remaining = sum(record['status'] in {'quarantined', 'pending'} for record in document['items'])
            trash_tree.insert('', 'end', iid=item['id'], values=(f'{remaining} saved folders', size_label(item['bytes']), item['id']))
        trash_summary.set(f"{len(batches)} batches | {size_label(sum(item['bytes'] for item in batches))} in Studio Trash")

    def selection_summary(*args):
        selected = [state['items'][int(key)] for key in preview_tree.selection()]
        summary.set(f"{len(selected)} folders selected | {size_label(sum(item['bytes'] for item in selected))} | Move to Trash to keep a restore option.")

    def launch(operation, callback):
        if state['busy']:
            return
        state['busy'] = True
        for button in buttons:
            button.config(state='disabled')
        status.set(operation)
        def worker():
            try:
                result = callback()
                events.put(('done', result))
            except Exception as error:
                events.put(('error', str(error)))
        threading.Thread(target=worker, daemon=True).start()

    def scan():
        try:
            minimum = int(days.get())
            if minimum < 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror('Check age', 'Enter zero or a positive whole number of days.', parent=window)
            return
        state['settings'] = dict(days=minimum, caches=caches.get(), logs=logs.get())
        launch('Scanning generated files...', lambda: dict(scan=cleaner.scan(**state['settings']), batches=cleaner.batches()))

    def move():
        items = [state['items'][int(key)] for key in preview_tree.selection()]
        if not items:
            messagebox.showinfo('Select files', 'Scan and select the folders you want to move to Trash.', parent=window)
            return
        def operation():
            document = cleaner.quarantine(items)
            return dict(scan=cleaner.scan(**state['settings']), batches=cleaner.batches(), errors=document['errors'],
                        message='Selected folders moved to Studio Trash.')
        launch('Moving selected folders to Studio Trash...', operation)

    def restore():
        batches = list(trash_tree.selection())
        if not batches:
            return
        def operation():
            errors = []
            for batch in batches:
                errors.extend(cleaner.restore(batch)['errors'])
            return dict(scan=cleaner.scan(**state['settings']), batches=cleaner.batches(), errors=errors,
                        message='Restore finished. Existing files were preserved.')
        launch('Restoring selected batches...', operation)

    def purge():
        batches = list(trash_tree.selection())
        if not batches:
            return
        if not messagebox.askyesno('Permanently empty selected Trash',
                f'Delete {len(batches)} selected trash batches permanently?\n\nThis frees disk space and cannot be undone.', parent=window):
            return
        def operation():
            amount = sum(cleaner.purge(batch)['bytes'] for batch in batches)
            return dict(batches=cleaner.batches(), message=f'Permanently removed {size_label(amount)} from Studio Trash.')
        launch('Emptying selected Studio Trash...', operation)

    for frame, label, command, primary in [
        (review_actions, 'Scan', scan, True),
        (review_actions, 'Select all', lambda: preview_tree.selection_set(preview_tree.get_children()), False),
        (review_actions, 'Move selected to Trash', move, False),
        (trash_actions, 'Refresh', lambda: launch('Loading Trash...', lambda: dict(batches=cleaner.batches())), False),
        (trash_actions, 'Restore selected', restore, True),
        (trash_actions, 'Empty selected permanently', purge, False),
    ]:
        button = ttk.Button(frame, text=label, command=command, style='Accent.TButton' if primary else 'TButton')
        button.pack(side='left', padx=(0, 8))
        buttons.append(button)

    def poll():
        if state['closed']:
            return
        try:
            kind, result = events.get_nowait()
        except queue.Empty:
            window.after(100, poll)
            return
        state['busy'] = False
        for button in buttons:
            button.config(state='normal')
        if kind == 'error':
            status.set('Operation stopped. Review the message before trying again.')
            messagebox.showerror('Cleaner', result, parent=window)
        else:
            if 'scan' in result:
                state['items'] = result['scan']['items']
                preview_tree.delete(*preview_tree.get_children())
                for index, item in enumerate(state['items']):
                    preview_tree.insert('', 'end', iid=str(index), values=(item['kind'], size_label(item['bytes']), item['relative']))
                preview_tree.selection_set(preview_tree.get_children())
                selection_summary()
            fill_trash(result['batches'])
            status.set(result.get('message', 'Scan finished. Review your selection before moving files.'))
            if result.get('errors'):
                messagebox.showinfo('Some items were skipped', '\n'.join(result['errors'][:15]), parent=window)
        window.after(100, poll)

    def close():
        if state['busy']:
            messagebox.showinfo('Cleaner is working', 'Wait for this operation to finish before closing.', parent=window)
            return
        state['closed'] = True
        window.grab_release()
        window.destroy()
        on_close()

    preview_tree.bind('<<TreeviewSelect>>', selection_summary)
    window.protocol('WM_DELETE_WINDOW', close)
    window.after(100, poll)
    return window

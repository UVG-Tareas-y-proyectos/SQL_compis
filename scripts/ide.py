"""IDE SQL con el mismo recorrido visual que el proyecto de Compiscript."""

from pathlib import Path
import re
import sys
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from sqlcompis.pipeline import SQLEngine
from sqlcompis.model import Node, SyntaxNode, SQLError
from sqlcompis.frontend import KEYWORDS

BG, PANEL, EDITOR, FG = '#0b1020', '#111827', '#090e1a', '#e5e7eb'
EXAMPLES = ROOT / 'examples'


class SQLIDE(tk.Tk):
    def __init__(self, database=None):
        super().__init__()
        self.title('SQL Compis - Intérprete con archivos')
        self.geometry('1450x900')
        self.minsize(1080, 680)
        self.configure(bg=BG)
        self.engine = SQLEngine(database or ROOT / 'database')
        self.result = None
        self.file_path = None
        self.font = ('Consolas', 11)
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TNotebook', background=PANEL)
        style.configure('TNotebook.Tab', padding=(10, 7))
        style.configure('Treeview', rowheight=25, background=EDITOR, foreground=FG, fieldbackground=EDITOR, font=('Consolas', 10))
        self._build()
        self.bind('<F5>', lambda event: self.analyze())
        self.bind('<F6>', lambda event: self.execute())
        self.bind('<Control-s>', lambda event: self.save_file())
        self.load_example('demo_completa')

    def _build(self):
        toolbar = tk.Frame(self, bg=BG, padx=12, pady=10)
        toolbar.pack(fill='x')
        tk.Label(toolbar, text='SQL Compis', font=('Segoe UI', 18, 'bold'), bg=BG, fg=FG).pack(side='left', padx=(0,12))
        for text, action in [('Abrir', self.open_file), ('Guardar', self.save_file),
                             ('Base de datos', self.choose_database), ('Demo nueva', self.new_demo),
                             ('Analizar (F5)', self.analyze), ('Ejecutar (F6)', self.execute)]:
            tk.Button(toolbar, text=text, command=action, bg=PANEL, fg=FG, padx=8, pady=6, relief='flat').pack(side='left', padx=3)
        self.example_name = tk.StringVar(value='demo_completa')
        combo = ttk.Combobox(toolbar, textvariable=self.example_name, state='readonly', width=24,
                             values=sorted(p.stem for p in EXAMPLES.glob('*.sql')))
        combo.pack(side='right')
        combo.bind('<<ComboboxSelected>>', lambda event: self.load_example(self.example_name.get()))
        self.database_label = tk.Label(self, anchor='w', bg=PANEL, fg='#94a3b8', padx=12, pady=7)
        self.database_label.pack(fill='x')
        self._database_label()
        panes = tk.PanedWindow(self, orient='horizontal', bg=BG, sashwidth=7)
        panes.pack(fill='both', expand=True, padx=10, pady=10)
        editor_frame = tk.Frame(panes, bg=PANEL)
        panes.add(editor_frame, minsize=390, stretch='always')
        scroll = ttk.Scrollbar(editor_frame)
        scroll.pack(side='right', fill='y')
        self.editor = tk.Text(editor_frame, font=self.font, bg=EDITOR, fg=FG, insertbackground='#22c55e',
                              undo=True, wrap='none', padx=10, pady=10, yscrollcommand=scroll.set)
        self.editor.pack(fill='both', expand=True)
        scroll.configure(command=self.editor.yview)
        self.editor.bind('<KeyRelease>', self.highlight)
        for tag, color in [('keyword','#c084fc'),('string','#86efac'),('comment','#64748b')]:
            self.editor.tag_configure(tag, foreground=color)
        self.editor.tag_configure('error_line', background='#4c1523')
        self.notebook = ttk.Notebook(panes)
        panes.add(self.notebook, minsize=560, stretch='always')
        self.frames = {}
        for label in ['Tokens','Árbol sintáctico','AST','Errores','Resultados','Plan de acceso']:
            frame = tk.Frame(self.notebook, bg=PANEL)
            self.frames[label] = frame
            self.notebook.add(frame, text=label)
        self.token_tree = self.tree(self.frames['Tokens'], ['Token','Lexema','Línea','Columna'])
        self.syntax_tree = self.tree(self.frames['Árbol sintáctico'], ['Línea'], hierarchical=True)
        self.ast_tree = self.tree(self.frames['AST'], ['Línea'], hierarchical=True)
        self.error_tree = self.tree(self.frames['Errores'], ['Fase','Línea','Columna','Mensaje'])
        self.error_tree.bind('<<TreeviewSelect>>', self.go_to_error)
        self.plan_tree = self.tree(self.frames['Plan de acceso'], ['Sentencia','Tabla','Alias','Acceso','Índices','Leídas','Total'])
        result_frame = self.frames['Resultados']
        self.result_choice = ttk.Combobox(result_frame, state='readonly')
        self.result_choice.pack(fill='x', padx=5, pady=5)
        self.result_choice.bind('<<ComboboxSelected>>', lambda event: self.show_selected_result())
        grid_frame = tk.Frame(result_frame)
        grid_frame.pack(fill='both', expand=True)
        self.result_tree = self.tree(grid_frame, [])
        self.result_message = tk.Label(result_frame, text='', anchor='w', bg=PANEL, fg=FG, padx=10, pady=8, wraplength=650)
        self.result_message.pack(fill='x')
        self.status = tk.Label(self, text='Listo', bg=PANEL, fg='#94a3b8', anchor='w', padx=12, pady=8)
        self.status.pack(fill='x')

    def tree(self, parent, columns, hierarchical=False):
        tree = ttk.Treeview(parent, columns=columns, show='tree headings' if hierarchical else 'headings')
        if hierarchical:
            tree.heading('#0', text='Nodo')
            tree.column('#0', width=430)
        for column in columns:
            tree.heading(column, text=column)
            tree.column(column, width=70 if column in {'Línea','Columna','Leídas','Total'} else 155, stretch=True)
        vertical = ttk.Scrollbar(parent, command=tree.yview)
        horizontal = ttk.Scrollbar(parent, orient='horizontal', command=tree.xview)
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        tree.grid(row=0, column=0, sticky='nsew')
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        return tree

    def _database_label(self):
        self.database_label.configure(text=f'Base de datos: {self.engine.storage.root}')

    def load(self, text, path=None):
        self.editor.delete('1.0', 'end')
        self.editor.insert('1.0', text)
        self.file_path = path
        self.highlight()

    def load_example(self, name):
        path = EXAMPLES / f'{name}.sql'
        if path.exists():
            self.load(path.read_text(encoding='utf-8-sig'), path)
            self.analyze()

    def open_file(self):
        path = filedialog.askopenfilename(filetypes=[('SQL','*.sql')], initialdir=EXAMPLES)
        if path:
            self.load(Path(path).read_text(encoding='utf-8-sig'), Path(path))
            self.analyze()

    def save_file(self):
        if self.file_path is None:
            path = filedialog.asksaveasfilename(defaultextension='.sql', filetypes=[('SQL','*.sql')])
            if not path:
                return
            self.file_path = Path(path)
        try:
            self.file_path.write_text(self.editor.get('1.0','end-1c'), encoding='utf-8')
        except OSError as exc:
            messagebox.showerror('Guardar', str(exc))

    def choose_database(self):
        path = filedialog.askdirectory(title='Seleccionar directorio de la base de datos')
        if path:
            try:
                self.engine = SQLEngine(path)
                self._database_label()
                self.analyze()
            except SQLError as exc:
                messagebox.showerror('Base de datos', str(exc.diagnostic))

    def new_demo(self):
        directory = ROOT / 'database_demos'
        directory.mkdir(exist_ok=True)
        path = tempfile.mkdtemp(prefix='demo_', dir=directory)
        self.engine = SQLEngine(path)
        self._database_label()
        self.example_name.set('demo_completa')
        self.load_example('demo_completa')
        self.status.configure(text='Base de demostración nueva. Presione Ejecutar (F6).')

    def highlight(self, event=None):
        source = self.editor.get('1.0','end-1c')
        patterns = [('keyword', r'\b('+'|'.join(KEYWORDS)+r')\b'),
                    ('string', r"'(?:''|[^'])*'"), ('comment', r'--[^\n]*|/\*[\s\S]*?\*/')]
        for tag, pattern in patterns:
            self.editor.tag_remove(tag,'1.0','end')
            for match in re.finditer(pattern, source, flags=re.IGNORECASE):
                self.editor.tag_add(tag,f'1.0+{match.start()}c',f'1.0+{match.end()}c')

    def analyze(self):
        self.result = self.engine.analyze(self.editor.get('1.0','end-1c'))
        self.render()
        if self.result.ok:
            self.status.configure(text='Análisis correcto. No se ejecutó ni modificó la base de datos.', fg='#22c55e')

    def execute(self):
        self.result = self.engine.execute(self.editor.get('1.0','end-1c'))
        self.render()
        if self.result.ok:
            self.status.configure(text=f'{len(self.result.results)} sentencia(s) ejecutada(s).', fg='#22c55e')
            self.notebook.select(self.frames['Resultados'])

    def render(self):
        for tree in [self.token_tree,self.syntax_tree,self.ast_tree,self.error_tree,self.plan_tree,self.result_tree]:
            tree.delete(*tree.get_children())
        for token in self.result.tokens:
            self.token_tree.insert('', 'end', values=(token.type,token.value,token.line,token.column))
        if self.result.tree:
            self.add_node(self.syntax_tree, self.result.tree)
        if self.result.ast:
            self.add_node(self.ast_tree, self.result.ast)
        self.editor.tag_remove('error_line','1.0','end')
        for diagnostic in self.result.diagnostics:
            self.error_tree.insert('', 'end', values=(diagnostic.phase,diagnostic.line,diagnostic.column,diagnostic.message))
            self.editor.tag_add('error_line',f'{diagnostic.line}.0',f'{diagnostic.line+1}.0')
        if not self.result.ok:
            self.status.configure(text=str(self.result.diagnostics[0]),fg='#fb7185')
            self.notebook.select(self.frames['Errores'])
        for i, result in enumerate(self.result.results, 1):
            for access in result.plan:
                self.plan_tree.insert('', 'end', values=(i,access['table'],access['alias'],access['access'],
                    ', '.join(access['indexes']),access['rows_read'],access['total_rows']))
        self.result_choice.configure(values=[f'{i}. {r.message}' for i,r in enumerate(self.result.results,1)])
        if self.result.results:
            self.result_choice.current(len(self.result.results)-1)
            self.show_selected_result()
        else:
            self.result_choice.set('')
            self.result_tree.configure(columns=[])
            self.result_message.configure(text='Sin resultados de ejecución.')

    def add_node(self, tree, node, parent='', label=None):
        if isinstance(node, SyntaxNode):
            item = tree.insert(parent,'end',text=node.rule,values=(node.line,),open=parent=='')
            for child in node.children:
                self.add_node(tree,child,item)
        elif isinstance(node, Node):
            item = tree.insert(parent,'end',text=node.kind,values=(node.line,),open=parent=='')
            for key, value in node.data.items():
                if isinstance(value, (Node,list)):
                    field = tree.insert(item,'end',text=key,open=False)
                    for child in value if isinstance(value,list) else [value]:
                        self.add_node(tree,child,field)
                else:
                    tree.insert(item,'end',text=f'{key}: {value}')
        else:
            tree.insert(parent,'end',text=f'{node.type}: {node.value}' if hasattr(node,'type') else str(node),values=(getattr(node,'line',''),))

    def show_selected_result(self):
        i = self.result_choice.current()
        if i < 0 or not self.result.results:
            return
        result = self.result.results[i]
        self.result_tree.delete(*self.result_tree.get_children())
        columns = [f'c{j}' for j in range(len(result.columns))]
        self.result_tree.configure(columns=columns)
        for key, name in zip(columns,result.columns):
            self.result_tree.heading(key,text=name)
            self.result_tree.column(key,width=140)
        for row in result.rows:
            values = ['NULL' if v is None else 'TRUE' if v is True else 'FALSE' if v is False else str(v) for v in row]
            self.result_tree.insert('','end',values=values)
        self.result_message.configure(text=result.message)

    def go_to_error(self, event=None):
        selection = self.error_tree.selection()
        if selection:
            phase, line, column, message = self.error_tree.item(selection[0],'values')
            self.editor.mark_set('insert', f'{line}.{max(int(column)-1,0)}')
            self.editor.see(f'{line}.0')
            self.editor.focus_set()


if __name__ == '__main__':
    SQLIDE().mainloop()

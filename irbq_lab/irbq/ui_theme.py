"""Light/dark palettes for ttk, classic Tk, and the embedded Matplotlib figure."""
from tkinter import ttk
import tkinter as tk

PALETTES={
 'light':dict(bg='#f2f4f7',panel='#ffffff',field='#ffffff',fg='#172638',muted='#5c6b7b',border='#d2d9e2',
              accent='#146b8a',select='#d8ebf4',hover='#e5edf4',disabled='#8793a0',grid='#a7b5c2',
              ref='#697785',model='#176dbe',sum='#a36718',target='#8b739c',bands=['#176dbe','#ba623b','#238575','#9273b1','#ab507e','#688d36','#947f30','#498c9a']),
 'dark':dict(bg='#171c23',panel='#202731',field='#151b23',fg='#e6edf6',muted='#a3b3c6',border='#394455',
             accent='#5cb8df',select='#324f66',hover='#2b3747',disabled='#6e7c8e',grid='#55677a',
             ref='#e2b66d',model='#6ab8ff',sum='#e2b66d',target='#e2b66d',bands=['#6ab8ff','#eda17c','#73d0b0','#b0a0ef','#ef91b5','#a6ce73','#e3c878','#7cd8e6'])
}

def apply_theme(root,name):
    c=PALETTES[name];root.colors=c
    style=ttk.Style(root)
    if style.theme_use()!='clam':style.theme_use('clam')
    style.configure('.',background=c['bg'],foreground=c['fg'],font=('Segoe UI',10),bordercolor=c['border'],
                    lightcolor=c['border'],darkcolor=c['border'],troughcolor=c['field'],focuscolor=c['accent'])
    style.configure('TFrame',background=c['bg'])
    style.configure('Card.TFrame',background=c['panel'])
    style.configure('TLabel',background=c['bg'],foreground=c['fg'])
    style.configure('Title.TLabel',font=('Segoe UI',17,'bold'))
    style.configure('Small.TLabel',foreground=c['muted'],font=('Segoe UI',9))
    style.configure('TButton',padding=(9,5),background=c['panel'],foreground=c['fg'],borderwidth=1)
    style.map('TButton',background=[('active',c['hover']),('pressed',c['select'])],foreground=[('disabled',c['disabled'])])
    style.configure('Accent.TButton',background=c['accent'],foreground=c['field'])
    style.map('Accent.TButton',background=[('active',c['select'])],foreground=[('active',c['fg'])])
    style.configure('TCheckbutton',background=c['bg'],foreground=c['fg'],indicatorbackground=c['field'])
    style.map('TCheckbutton',background=[('active',c['bg'])],foreground=[('disabled',c['disabled'])],indicatorbackground=[('selected',c['accent']),('!selected',c['field'])])
    style.configure('TRadiobutton',background=c['bg'],foreground=c['fg'],indicatorbackground=c['field'])
    style.map('TRadiobutton',background=[('active',c['bg'])])
    for name_ in ('TEntry','TCombobox','TSpinbox'):
        style.configure(name_,fieldbackground=c['field'],foreground=c['fg'],background=c['panel'],insertcolor=c['fg'],arrowcolor=c['fg'],padding=4)
        style.map(name_,fieldbackground=[('readonly',c['field']),('disabled',c['bg'])],foreground=[('disabled',c['disabled']),('readonly',c['fg'])],selectbackground=[('!disabled',c['select'])],selectforeground=[('!disabled',c['fg'])])
    style.configure('TNotebook',background=c['bg'],borderwidth=0)
    # Keep tab geometry invariant across normal/active/selected states. The clam
    # theme otherwise expands the selected tab, which makes the lower panel jump.
    style.configure('TNotebook.Tab',background=c['bg'],foreground=c['muted'],padding=(12,7),borderwidth=1,relief='flat')
    style.map('TNotebook.Tab',background=[('selected',c['panel']),('active',c['hover'])],foreground=[('selected',c['fg'])],
              padding=[('selected',(12,7)),('active',(12,7)),('!selected',(12,7))],
              expand=[('selected',(0,0,0,0)),('active',(0,0,0,0)),('!selected',(0,0,0,0))])
    style.configure('TLabelframe',background=c['bg'],bordercolor=c['border'])
    style.configure('TLabelframe.Label',background=c['bg'],foreground=c['muted'])
    style.configure('Treeview',background=c['field'],fieldbackground=c['field'],foreground=c['fg'],rowheight=27,borderwidth=0)
    style.map('Treeview',background=[('selected',c['select'])],foreground=[('selected',c['fg'])])
    style.configure('Treeview.Heading',background=c['panel'],foreground=c['fg'],padding=(6,6))
    style.map('Treeview.Heading',background=[('active',c['hover'])])
    style.configure('Horizontal.TScale',background=c['accent'],troughcolor=c['field'],bordercolor=c['border'],sliderlength=22,lightcolor=c['accent'],darkcolor=c['accent'])
    style.configure('TProgressbar',background=c['accent'],troughcolor=c['field'])
    style.configure('TScrollbar',background=c['panel'],arrowcolor=c['fg'],troughcolor=c['bg'])
    root.configure(background=c['bg'])
    root.option_add('*TCombobox*Listbox.background',c['field']);root.option_add('*TCombobox*Listbox.foreground',c['fg'])
    root.option_add('*TCombobox*Listbox.selectBackground',c['select']);root.option_add('*TCombobox*Listbox.selectForeground',c['fg'])
    theme_widgets(root,c)
    return c

def theme_widgets(widget,c):
    try:
        if isinstance(widget,(tk.Tk,tk.Toplevel,tk.Frame,tk.Canvas)):
            widget.configure(background=c['bg'])
        if isinstance(widget,tk.Text):
            widget.configure(background=c['field'],foreground=c['fg'],insertbackground=c['fg'],selectbackground=c['select'],relief='flat')
        if isinstance(widget,tk.Menu):
            widget.configure(background=c['panel'],foreground=c['fg'],activebackground=c['select'],activeforeground=c['fg'],selectcolor=c['accent'])
        if isinstance(widget,tk.Listbox):
            widget.configure(background=c['field'],foreground=c['fg'],selectbackground=c['select'],selectforeground=c['fg'])
    except tk.TclError:pass
    for child in widget.winfo_children():theme_widgets(child,c)

def theme_axes(figure,ax,c):
    figure.set_facecolor(c['panel']);ax.set_facecolor(c['panel'])
    ax.tick_params(colors=c['muted'],labelsize=9)
    for spine in ax.spines.values():spine.set_color(c['border'])
    ax.xaxis.label.set_color(c['muted']);ax.yaxis.label.set_color(c['muted']);ax.title.set_color(c['fg'])
    ax._left_title.set_color(c['fg']);ax._right_title.set_color(c['fg'])
    ax.grid(True,which='major',color=c['grid'],alpha=.28,linewidth=.7)
    ax.grid(True,which='minor',color=c['grid'],alpha=.12,linewidth=.5)
    for t in ax.texts:
        if t.get_gid()!='band-text':t.set_color(c['fg'])
    legend=ax.get_legend()
    if legend:
        legend.get_frame().set_facecolor(c['panel']);legend.get_frame().set_edgecolor(c['border'])
        for t in legend.get_texts():t.set_color(c['fg'])

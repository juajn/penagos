from extensions import db
from flask_login import UserMixin
from datetime import datetime

class Usuario(db.Model, UserMixin):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    nombre_completo = db.Column(db.String(100), nullable=False)
    documento = db.Column(db.String(20), unique=True, nullable=False)
    contraseña = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(20), nullable=False)  

    def __repr__(self):
        return f'<Usuario {self.nombre_completo} - {self.rol}>'

class Actividad(db.Model):
    __tablename__ = 'actividades'
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    turno = db.Column(db.String(20), nullable=False)
    hora_inicio = db.Column(db.String(10), nullable=False)
    hora_final = db.Column(db.String(10), nullable=False)
    codigo_actividad = db.Column(db.String(50), nullable=False)
    descripcion_actividad = db.Column(db.String(200))
    codigo_equipo = db.Column(db.String(50))
    orden_produccion = db.Column(db.String(50))
    referencia_producto = db.Column(db.String(100))
    cantidad_trabajada = db.Column(db.Integer)
    observaciones = db.Column(db.Text)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)

    usuario = db.relationship('Usuario', backref='actividades')

    def __repr__(self):
        return f'<Actividad {self.codigo_actividad} - {self.fecha}>'
    
    

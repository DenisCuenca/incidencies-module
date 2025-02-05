from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import List, Optional
from uuid import uuid4
from sqlalchemy import create_engine, Column, String, Date, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
import os
import base64
from datetime import date
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import mimetypes

# Configuración de Base de Datos
DATABASE_URL = "sqlite:///./incidencias.db"
Base = declarative_base()
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Modelo de Usuario (para la relación)
class Usuario(Base):
    __tablename__ = "usuarios"
    id_usuario = Column(String, primary_key=True, index=True, default=lambda: str(uuid4()))
    nombre = Column(String, nullable=False)

# Modelo de Incidencia
class Incidencia(Base):
    __tablename__ = "incidencias"

    id_incidencia = Column(String, primary_key=True, index=True, default=lambda: str(uuid4()))
    id_usuario_emisor = Column(String, ForeignKey("usuarios.id_usuario"), nullable=False)
    id_catalogo = Column(String, nullable=False)
    subcategoria = Column(String, nullable=False)
    asunto = Column(String, nullable=False)
    descripcion = Column(Text, nullable=False)
    imagen = Column(String, nullable=True)
    video = Column(String, nullable=True)
    audio = Column(String, nullable=True)
    fecha_emision = Column(Date, nullable=False)
    ubicacion_lat = Column(String, nullable=True)
    ubicacion_lng = Column(String, nullable=True)
    status = Column(String, default="pending")  # Nuevo campo de estado

    usuario = relationship("Usuario")

Base.metadata.create_all(bind=engine)

app = FastAPI()

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directorios para almacenar archivos
UPLOAD_DIR = "./uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


@app.middleware("http")
async def redirect_to_https(request: Request, call_next):
    if request.url.scheme == "http":
        return RedirectResponse(url=str(request.url).replace("http://", "https://"), status_code=308)
    return await call_next(request)


# Modelos Pydantic
class IncidenciaCreate(BaseModel):
    id_usuario_emisor: str
    id_catalogo: str
    subcategoria: str
    asunto: str
    descripcion: str
    fecha_emision: Optional[date] = date.today()
    imagen: Optional[str] = None
    video: Optional[str] = None
    audio: Optional[str] = None
    ubicacion: Optional[dict] = None

class IncidenciaResponse(BaseModel):
    id_incidencia: str
    id_usuario_emisor: str
    id_catalogo: str
    subcategoria: str
    asunto: str
    descripcion: str
    imagen: Optional[str] = None
    video: Optional[str] = None
    audio: Optional[str] = None
    fecha_emision: str
    ubicacion: Optional[dict] = None
    status: str

class EstadoUpdate(BaseModel):
    status: str

# Función para obtener la sesión de BD
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Función para guardar archivos base64
def save_base64_file(base64_data: str, upload_dir: str) -> str:
    try:
        header, data = base64_data.split(",", 1)
        mime_type = header.split(":")[1].split(";")[0]
        extension = mimetypes.guess_extension(mime_type) or ".bin"

        file_data = base64.b64decode(data)
        file_name = f"{str(uuid4())}{extension}"
        file_path = os.path.join(upload_dir, file_name)

        os.makedirs(upload_dir, exist_ok=True)

        with open(file_path, "wb") as f:
            f.write(file_data)

        return file_path
    except Exception as e:
        raise ValueError(f"Error procesando archivo: {str(e)}")

# Endpoints

@app.post("/incidencias/", response_model=dict)
def create_incidencia(incidencia: IncidenciaCreate, db: Session = Depends(get_db)):
    try:
        ubicacion_lat = incidencia.ubicacion.get('lat') if incidencia.ubicacion else None
        ubicacion_lng = incidencia.ubicacion.get('lng') if incidencia.ubicacion else None

        nueva_incidencia = Incidencia(
            id_usuario_emisor=incidencia.id_usuario_emisor,
            id_catalogo=incidencia.id_catalogo,
            subcategoria=incidencia.subcategoria,
            asunto=incidencia.asunto,
            descripcion=incidencia.descripcion,
            fecha_emision=incidencia.fecha_emision,
            ubicacion_lat=str(ubicacion_lat) if ubicacion_lat else None,
            ubicacion_lng=str(ubicacion_lng) if ubicacion_lng else None
        )

        if incidencia.imagen:
            nueva_incidencia.imagen = save_base64_file(incidencia.imagen, os.path.join(UPLOAD_DIR, "images"))
        if incidencia.video:
            nueva_incidencia.video = save_base64_file(incidencia.video, os.path.join(UPLOAD_DIR, "videos"))
        if incidencia.audio:
            nueva_incidencia.audio = save_base64_file(incidencia.audio, os.path.join(UPLOAD_DIR, "audios"))

        db.add(nueva_incidencia)
        db.commit()
        db.refresh(nueva_incidencia)

        return {"message": "Incidencia creada correctamente", "id_incidencia": nueva_incidencia.id_incidencia}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/incidencias/", response_model=List[IncidenciaResponse])
def list_incidencias(request: Request, db: Session = Depends(get_db)):
    incidencias = db.query(Incidencia).all()
    base_url = str(request.base_url)

    return [
        IncidenciaResponse(
            id_incidencia=inc.id_incidencia,
            id_usuario_emisor=inc.id_usuario_emisor,
            id_catalogo=inc.id_catalogo,
            subcategoria=inc.subcategoria,
            asunto=inc.asunto,
            descripcion=inc.descripcion,
            imagen=f"{base_url}uploads/{os.path.basename(inc.imagen)}" if inc.imagen else None,
            video=f"{base_url}uploads/{os.path.basename(inc.video)}" if inc.video else None,
            audio=f"{base_url}uploads/{os.path.basename(inc.audio)}" if inc.audio else None,
            fecha_emision=inc.fecha_emision.strftime('%Y-%m-%d'),
            ubicacion={"lat": float(inc.ubicacion_lat), "lng": float(inc.ubicacion_lng)} if inc.ubicacion_lat and inc.ubicacion_lng else None,
            status=inc.status
        )
        for inc in incidencias
    ]


@app.get("/incidencias/", response_model=List[IncidenciaResponse])
def list_incidencias(
    request: Request, 
    db: Session = Depends(get_db), 
    id_usuario: Optional[int] = None  # Parámetro opcional en la consulta
):
    query = db.query(Incidencia)
    
    if id_usuario:  # Filtrar si se envía id_usuario
        query = query.filter(Incidencia.id_usuario_emisor == id_usuario)
    
    incidencias = query.all()
    base_url = str(request.base_url)

    return [
        IncidenciaResponse(
            id_incidencia=inc.id_incidencia,
            id_usuario_emisor=inc.id_usuario_emisor,
            id_catalogo=inc.id_catalogo,
            subcategoria=inc.subcategoria,
            asunto=inc.asunto,
            descripcion=inc.descripcion,
            imagen=f"{base_url}uploads/{os.path.basename(inc.imagen)}" if inc.imagen else None,
            video=f"{base_url}uploads/{os.path.basename(inc.video)}" if inc.video else None,
            audio=f"{base_url}uploads/{os.path.basename(inc.audio)}" if inc.audio else None,
            fecha_emision=inc.fecha_emision.strftime('%Y-%m-%d'),
            ubicacion={"lat": float(inc.ubicacion_lat), "lng": float(inc.ubicacion_lng)} if inc.ubicacion_lat and inc.ubicacion_lng else None,
            status=inc.status
        )
        for inc in incidencias
    ]


@app.patch("/incidencias/{id_incidencia}/estado", response_model=dict)
def update_incidencia_status(id_incidencia: str, estado_update: EstadoUpdate, db: Session = Depends(get_db)):
    incidencia = db.query(Incidencia).filter(Incidencia.id_incidencia == id_incidencia).first()
    if not incidencia:
        raise HTTPException(status_code=404, detail="Incidencia no encontrada")

    incidencia.status = estado_update.status
    db.commit()
    return {"message": f"Estado de incidencia cambiado a {estado_update.status}"}

@app.delete("/incidencias/{id_incidencia}", response_model=dict)
def delete_incidencia(id_incidencia: str, db: Session = Depends(get_db)):
    incidencia = db.query(Incidencia).filter(Incidencia.id_incidencia == id_incidencia).first()
    if not incidencia:
        raise HTTPException(status_code=404, detail="Incidencia no encontrada")

    db.delete(incidencia)
    db.commit()
    return {"message": "Incidencia eliminada correctamente"}

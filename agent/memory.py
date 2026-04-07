# agent/memory.py — Memoria de conversaciones con SQLite
# Generado por AgentKit para Elara

"""
Sistema de memoria del agente. Guarda el historial de conversaciones
por numero de telefono usando SQLite (local) o PostgreSQL (produccion).
"""

import os
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, DateTime, select, Integer
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./elara.db")

if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Mensaje(Base):
    """Modelo de mensaje en la base de datos."""
    __tablename__ = "mensajes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefono: Mapped[str] = mapped_column(String(50), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ContactoConocido(Base):
    """Mapeo de JIDs @lid a numeros reales de WhatsApp."""
    __tablename__ = "contactos_conocidos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lid_jid: Mapped[str] = mapped_column(String(100), index=True, unique=True)
    numero: Mapped[str] = mapped_column(String(50))
    nombre: Mapped[str] = mapped_column(String(200), default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


async def inicializar_db():
    """Crea las tablas si no existen."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def guardar_mensaje(telefono: str, role: str, content: str):
    """Guarda un mensaje en el historial de conversacion."""
    async with async_session() as session:
        mensaje = Mensaje(
            telefono=telefono,
            role=role,
            content=content,
            timestamp=datetime.utcnow()
        )
        session.add(mensaje)
        await session.commit()


async def obtener_historial(telefono: str, limite: int = 20) -> list[dict]:
    """
    Recupera los ultimos N mensajes de una conversacion.
    Retorna lista de diccionarios con role y content en orden cronologico.
    """
    async with async_session() as session:
        query = (
            select(Mensaje)
            .where(Mensaje.telefono == telefono)
            .order_by(Mensaje.timestamp.desc())
            .limit(limite)
        )
        result = await session.execute(query)
        mensajes = result.scalars().all()
        mensajes.reverse()
        return [
            {"role": msg.role, "content": msg.content}
            for msg in mensajes
        ]


async def limpiar_historial(telefono: str):
    """Borra todo el historial de una conversacion."""
    async with async_session() as session:
        query = select(Mensaje).where(Mensaje.telefono == telefono)
        result = await session.execute(query)
        mensajes = result.scalars().all()
        for msg in mensajes:
            await session.delete(msg)
        await session.commit()


# ── Contactos conocidos (@lid → numero real) ──

async def guardar_contacto(lid_jid: str, numero: str, nombre: str = ""):
    """Guarda o actualiza el mapeo @lid → numero real."""
    async with async_session() as session:
        query = select(ContactoConocido).where(ContactoConocido.lid_jid == lid_jid)
        result = await session.execute(query)
        contacto = result.scalar_one_or_none()
        if contacto:
            contacto.numero = numero
            contacto.nombre = nombre or contacto.nombre
            contacto.timestamp = datetime.utcnow()
        else:
            contacto = ContactoConocido(
                lid_jid=lid_jid,
                numero=numero,
                nombre=nombre,
                timestamp=datetime.utcnow()
            )
            session.add(contacto)
        await session.commit()


async def buscar_por_lid(lid_jid: str) -> str | None:
    """Busca el numero real de un contacto por su JID @lid."""
    async with async_session() as session:
        query = select(ContactoConocido).where(ContactoConocido.lid_jid == lid_jid)
        result = await session.execute(query)
        contacto = result.scalar_one_or_none()
        if contacto:
            return contacto.numero
        return None


async def obtener_todos_contactos() -> dict[str, str]:
    """Retorna todos los mapeos @lid → numero como diccionario."""
    async with async_session() as session:
        query = select(ContactoConocido)
        result = await session.execute(query)
        contactos = result.scalars().all()
        return {c.lid_jid: c.numero for c in contactos}

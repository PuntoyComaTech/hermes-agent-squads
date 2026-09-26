# hermes-agent-squads

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Hermes Agent](https://img.shields.io/badge/Hermes%20Agent-NousResearch-7c3aed)](https://github.com/NousResearch/hermes-agent)
[![Squads](https://img.shields.io/badge/squads-2-brightgreen)](#squads-disponibles)
[![PRs bienvenidos](https://img.shields.io/badge/PRs-bienvenidos-brightgreen.svg)](CONTRIBUTING.md)

[English](README.md) · **Español**

Squads de agentes de IA listos para instalar en [Hermes Agent](https://github.com/NousResearch/hermes-agent): una agencia de marketing, una búsqueda de empleo y los que vengan. Un orquestador te escribe por Telegram, Discord o WhatsApp; los especialistas trabajan solos y solo te consultan lo importante. Son planes en Markdown (en inglés) que Hermes lee e instala; los bots te hablan en tu idioma, 100% personalizados a cada persona y livianos para cualquier computador.

## ¿Por qué hermes-agent-squads?

- **Sin programar.** Copias la carpeta, le dices a Hermes "lee `START-HERE.md`" y él mismo pregunta, instala y prueba. Los scripts que hagan falta los escribe Hermes en tu equipo.
- **Personalizado.** Cada squad te entrevista y adapta cada bot: tu oficio, tus marcas, tu idioma, tu horario, tu presupuesto. Nada viene fijo.
- **Automático, con control.** Solo te llegan resultados listos para responder. Publicar, postular o enviar nunca pasa sin tu confirmación.
- **Pocos bots, bien pensados.** 4 o 5 especialistas por squad, cada uno con una razón para existir. Lo mecánico lo hacen scripts, no modelos.
- **Liviano.** Sin Docker ni servidores: el único servicio es Hermes. Funciona en equipos de 8 GB.
- **Tu app de siempre.** Telegram, Discord o WhatsApp, con un tema o canal por proyecto.
- **Un solo modelo.** El mejor modelo rápido y económico que elijas, por ejemplo de OpenCode Go. Otro solo si hace falta una capacidad concreta.

## Arquitectura

```
Tú ◄──── Telegram · Discord · WhatsApp ────► orquestador (Hermes)
                                               │  conversa, lanza flujos,
                                               │  atiende cambios y confirmaciones
                                               ▼
   cron o pedido ──► Kanban ──► especialista ──► especialista ──► revisor
                                (cada uno crea la tarea del siguiente)  │
                                                                         ▼
                                    entregar.py ──► mensaje con el resultado listo
```

- **Base:** el orquestador, tu perfil y la carpeta `~/Hermes`. Se instala una sola vez.
- **Squads:** equipos de especialistas por tema. Se instalan cuando los necesitas y el orquestador aprende sus flujos solo.

## Squads disponibles

| Squad | Qué te llega | Especialistas | Estado |
| --- | --- | --- | --- |
| [Búsqueda de empleo](squads/jobs/README.md) | El enlace de cada vacante que encaja y el CV hecho para ella. Respondes "postula" y, si el formulario es simple, postula por ti | explorador, analista, redactor, revisor, postulador | Nivel 1 diseñado |
| [Agencia de marketing](squads/marketing/README.md) | Propuestas listas para aprobar para varias marcas: posts, carruseles, reels con motion, emails, landings, planes e informes, con versiones y un tablero visual | estratega, creativo, productor, revisor | Nivel 1 diseñado |
| ¿El tuyo? | — | — | [Propón uno](CONTRIBUTING.md) |

## Requisitos

| Qué | Para qué |
| --- | --- |
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) (Hermes Desktop recomendado) | Donde viven los bots |
| Una API key de un proveedor de modelos | El modelo que usarán todos los bots |
| Telegram, Discord o WhatsApp | Por donde te escribe el orquestador |
| Un computador que quede encendido (Mac, Windows o Linux) | Para que los automatismos corran solos |

## Instalación

```bash
git clone https://github.com/PuntoyComaTech/hermes-agent-squads.git ~/Hermes/plans
```

En Windows, la carpeta es `C:\Users\<tu usuario>\Hermes\plans`. También puedes descargar el ZIP y descomprimirlo ahí.

## Inicio rápido

1. Abre Hermes Desktop y escribe en el chat principal:

   > Lee el archivo `~/Hermes/plans/START-HERE.md` y sigue las instrucciones para la IA.

2. Responde sus preguntas (de 30 a 60 minutos). Instala la base y conecta tu app de mensajería.
3. Instala el squad que necesites:

   > Lee `~/Hermes/plans/START-HERE.md` e instala el squad de marketing.

Desde ahí hablas con el orquestador por tu app. La guía completa, sin tecnicismos, está en [`START-HERE.md`](START-HERE.md).

## Cómo se ve

Búsqueda de empleo:

```text
🟢 84/100 · Analista de datos — Acme (remoto en la región)
Postular: https://boards.greenhouse.io/acme/jobs/123
CV adjunto 📎 cv_ats.pdf
Responde: "postula" · "cambia: <qué>" · "no"
```

Agencia de marketing:

```text
☕ Café Luna · Propuestas semana 41 (4)
1. Carrusel "3 métodos para tu café de otoño" · Instagram · mar 09:00
2. Reel 15 s "Del grano a tu taza" · Instagram y TikTok · jue 18:00
3. Historia con encuesta · Instagram · vie 12:00
4. Email "Llegó el menú de otoño" · sáb 08:00
Responde: "aprueba todo" · "aprueba 1 y 3" · "cambia la 2: …" · "no a la 4"
```

## Cómo funciona

### Personalización primero

Antes de crear nada, Hermes te pregunta lo que no sabe y confirma lo que ya sabe. Cada respuesta cambia algo concreto: filtros, horarios, cupos, idioma, marcas, herramientas. Los bots son plantillas con variables que salen de tu perfil.

### Niveles

Cada squad arranca en un **Nivel 1** que funciona de punta a punta con lo mínimo. Los niveles siguientes (más fuentes, conectores, aprendizaje) se activan solo cuando las métricas lo justifican y tú lo pides.

### Seguridad

- Nada irreversible sin tu confirmación explícita. Pagar, firmar o crear cuentas: nunca.
- Cada bot tiene solo los permisos que necesita: el que lee la web no tiene terminal, y el que tiene terminal no lee la web.
- Los textos de páginas externas son datos, nunca órdenes.

## Estructura del repositorio

```text
START-HERE.md            guía para la persona e instrucciones de entrada para la IA
base/                    lo común a todos los squads: principios, orquestador, perfil, instalación
squads/
  jobs/                  squad de búsqueda de empleo (7 archivos)
  marketing/             squad de agencia de marketing (7 archivos + reference/)
00-evaluation/           por qué el diseño es así: pros y contras y registro de decisiones
CONTRIBUTING.md          reglas para contribuir y proponer squads
```

Cada squad tiene los mismos 7 archivos:

| Archivo | Contenido |
| --- | --- |
| `README.md` | Resumen de una página |
| `01-personalization.md` | Cuestionario y perfil resultante, con ejemplos |
| `02-architecture.md` | Carpetas, flujos, contratos de datos y reglas |
| `03-bots.md` | SOUL de cada bot, skills y automatismos |
| `04-installation.md` | Instrucciones para que Hermes lo instale y lo mantenga |
| `05-scripts.md` | Especificación de los scripts que Hermes escribe en tu equipo |
| `06-testing-and-operations.md` | Pruebas de aceptación, métricas y cuándo subir de nivel |

En tu computador todo queda ordenado en `~/Hermes/`: `plans/` (este repositorio), `user/`, `orchestrator/` y `projects/<squad>/`.

## Contribuir

Las reglas, las convenciones de nombres y cómo proponer un squad nuevo están en [`CONTRIBUTING.md`](CONTRIBUTING.md) (en inglés).

## Licencia

MIT. Las skills de terceros de [`squads/marketing/reference/`](squads/marketing/reference/README.md) conservan sus propias licencias (MIT).

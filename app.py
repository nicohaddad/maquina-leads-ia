import streamlit as st
import pandas as pd
import googlemaps
from google import genai
import requests
from io import BytesIO
import time
import base64
from PIL import Image
import json
import os
from googlesearch import search

COST_FILE = "costos_historicos.json"

def cargar_costo_historico():
    if os.path.exists(COST_FILE):
        try:
            with open(COST_FILE, "r") as f:
                data = json.load(f)
                return data.get("costo_total", 0.0)
        except:
            return 0.0
    return 0.0

def agregar_costo_historico(nuevo_costo):
    costo_actual = cargar_costo_historico()
    costo_total = costo_actual + nuevo_costo
    try:
        with open(COST_FILE, "w") as f:
            json.dump({"costo_total": costo_total}, f)
    except:
        pass
    return costo_total

# Configuración de la página
st.set_page_config(page_title="Máquina de Prospección IA", page_icon="🤖", layout="wide", initial_sidebar_state="collapsed")

# Inyectar CSS personalizado para que se vea más moderno
st.markdown("""
<style>
    /* Mejorar botones */
    .stButton>button {
        border-radius: 8px;
        font-weight: bold;
        transition: 0.3s;
    }
    /* Tarjetas de métricas */
    div[data-testid="metric-container"] {
        background-color: rgba(28, 131, 225, 0.1);
        border: 1px solid rgba(28, 131, 225, 0.1);
        padding: 5% 5% 5% 10%;
        border-radius: 8px;
        color: rgb(30, 103, 119);
        overflow-wrap: break-word;
    }
</style>
""", unsafe_allow_html=True)

# Título y descripción
col_title1, col_title2 = st.columns([3, 1])
with col_title1:
    st.title("🤖 Máquina Automática de Prospección")
    st.markdown("Encuentra negocios, evalúa su presencia digital con Inteligencia Artificial y genera correos de ventas hiper-personalizados en minutos.")

# Inicializar estado para guardar resultados y no perderlos
if 'resultados' not in st.session_state:
    st.session_state.resultados = None
if 'total_tokens' not in st.session_state:
    st.session_state.total_tokens = 0
if 'costo_estimado' not in st.session_state:
    st.session_state.costo_estimado = 0.0

# Crear Pestañas Principales para limpiar la interfaz
tab_busqueda, tab_config = st.tabs(["🔍 Búsqueda y Resultados", "⚙️ Configuración del Motor IA"])

with col_title2:
    st.metric("💸 Consumo Total Histórico", f"${cargar_costo_historico():.4f} USD")

# ==========================================
# PESTAÑA 2: CONFIGURACIÓN (Ocultamos lo técnico aquí)
# ==========================================
with tab_config:
    st.header("Configuración Avanzada")
    st.markdown("Ajusta las llaves, los criterios de evaluación y los mensajes de la IA.")
    
    col_conf1, col_conf2 = st.columns(2)
    
    with col_conf1:
        st.subheader("🔑 Claves API")
        default_gmaps = st.secrets["GMAPS_API_KEY"] if "GMAPS_API_KEY" in st.secrets else ""
        default_gemini = st.secrets["GEMINI_API_KEY"] if "GEMINI_API_KEY" in st.secrets else ""
        gmaps_api_key = st.text_input("Google Maps API Key", value=default_gmaps, type="password")
        gemini_api_key = st.text_input("Gemini API Key", value=default_gemini, type="password")
        
        st.subheader("⭐ Filtros de Calidad de Google Maps")
        min_rating = st.slider("Rating Mínimo", 0.0, 5.0, 0.0, 0.5)
        max_rating = st.slider("Rating Máximo", 0.0, 5.0, 5.0, 0.5)

    with col_conf2:
        st.subheader("🧠 Matriz de Lead Scoring")
        st.caption("Puntos otorgados a cada criterio para calcular el Score Final del lead.")
        c1, c2, c3 = st.columns(3)
        pts_resenas_altas = c1.number_input("100+ Reseñas", value=10)
        pts_resenas_medias = c2.number_input("30-99 Reseñas", value=6)
        pts_rating_alto = c3.number_input("Rating 4.6+", value=8)
        pts_no_web = c1.number_input("No tiene web", value=15)
        pts_web_mala = c2.number_input("Web mala/vieja", value=10)
        pts_premium = c3.number_input("Servs. premium", value=10)
        pts_marketing = c1.number_input("Ig activo", value=4)
        pts_whatsapp = c2.number_input("WhatsApp", value=7)
        pts_agenda = c3.number_input("Agenda/Citas", value=6)

    st.markdown("---")
    st.subheader("✍️ Personalización de Textos (Prompts)")
    p1, p2, p3 = st.columns(3)
    with p1:
        prompt_eval_input = st.text_area(
            "Prompt de Evaluación Visual",
            value="Eres un experto diseñador web. Revisa la captura de pantalla de esta página web. Evalúa si el diseño es moderno, o si parece antiguo, si tiene mala resolución o es poco profesional. Responde con una única palabra inicial: 'APROBADO' o 'RECHAZADO'. Luego, en la misma línea, escribe un guión '-' y da una breve razón de 1 sola frase del por qué.",
            height=200
        )
    with p2:
        prompt_email_input = st.text_area(
            "Correo (Tienen Web FEA)",
            value="Escribe un correo de ventas frío corto dirigido al dueño de '{business_name}'. Dile que visitaste su página web ({website_url}) y notaste lo siguiente: {evaluacion}. Ofrécele tus servicios de creación de páginas web con IA. Ofrece un prototipo gratis en 48h. Tono profesional, máximo 3 párrafos.",
            height=200
        )
    with p3:
        prompt_noweb_input = st.text_area(
            "Correo (NO Tienen Web)",
            value="Escribe un correo corto de ventas al dueño de '{business_name}'. Dile que los buscaste en internet y notaste que no tienen página web, lo cual les hace perder clientes. Ofrécele hacerles una web moderna con IA. Tono profesional.",
            height=90
        )
        prompt_caido_input = st.text_area(
            "Correo (Dominio Caído)",
            value="Escribe un correo URGENTE al dueño de '{business_name}'. Dile que intentaste entrar a su web ({website_url}) desde Google Maps pero está CAÍDA. Ofrécele hacerles una web nueva con IA hoy mismo.",
            height=90
        )

# ==========================================
# PESTAÑA 1: BÚSQUEDA Y RESULTADOS
# ==========================================
with tab_busqueda:
    st.markdown("### 🎯 Iniciar Nueva Prospección")
    
    col_busqueda1, col_busqueda2 = st.columns([2, 1])
    with col_busqueda1:
        search_query = st.text_input("¿A quién estás buscando hoy?", value="Estéticas en Polanco, CDMX", placeholder="Ej. Dentistas en Monterrey...")
    with col_busqueda2:
        max_results = st.number_input("Límite de negocios a extraer", min_value=1, max_value=20, value=5)
    
    solo_sin_web = st.checkbox("🚨 Filtro Estricto: Buscar SOLO negocios SIN página web (Ahorra tokens)", value=False)
    
    iniciar_btn = st.button("🚀 INICIAR PROSPECCIÓN AUTOMÁTICA", type="primary", use_container_width=True)



# --- FUNCIONES CORE ---

def get_places(query, api_key, max_results=5, min_rating=0.0, max_rating=5.0, solo_sin_web=False, console=None):
    """Obtiene los lugares usando Google Maps API, buscando en varias páginas si es necesario."""
    gmaps = googlemaps.Client(key=api_key)
    try:
        results = []
        if console: console.write(f"📡 Conectando a los servidores de Google Maps...")
        places_result = gmaps.places(query=query)
        pagina = 1
        
        while True:
            for place in places_result.get('results', []):
                if len(results) >= max_results:
                    break
                    
                place_id = place['place_id']
                # Obtener detalles completos
                details = gmaps.place(place_id, fields=['name', 'website', 'formatted_phone_number', 'rating', 'url', 'user_ratings_total'])['result']
                nombre = details.get('name', 'N/A')
                
                if console: console.write(f"👀 Revisando a: **{nombre}**...")
                
                rating = details.get('rating', 0.0)
                if not (min_rating <= rating <= max_rating):
                    if console: console.write(f"   ❌ Descartado: Rating muy bajo ({rating} estrellas).")
                    continue
                    
                website = details.get('website', 'No tiene')
                
                # --- PARCHE INTELIGENTE: BÚSQUEDA WEB EN VIVO ---
                if website == 'No tiene':
                    try:
                        search_term = f"{nombre} {query}"
                        if console: console.write(f"   🕵️‍♂️ Buscando '{nombre}' en la web oculta...")
                        for url_result in search(search_term, num_results=3, lang="es"):
                            directorios = ['facebook.com', 'instagram.com', 'foursquare', 'tripadvisor', 'yelp', 'linkedin', 'twitter', 'tiktok', 'youtube', 'doctoralia', 'maps.google', 'whatsapp.com', 'wa.me', 'topdoctors', 'guiadental']
                            if not any(d in url_result.lower() for d in directorios):
                                website = url_result
                                if console: console.write(f"   🔗 ¡Encontré su web escondida!: {website}")
                                break
                    except Exception as e:
                        pass
                
                if solo_sin_web and website != 'No tiene':
                    if console: console.write(f"   ❌ Descartado: Ya tiene página web ({website}).")
                    continue
                    
                if console: console.write(f"   ✅ **¡Prospecto Ideal Guardado!** ({len(results)+1}/{max_results})")
                results.append({
                    "Nombre": details.get('name', 'N/A'),
                    "Teléfono": details.get('formatted_phone_number', 'N/A'),
                    "Website": website,
                    "Rating": rating,
                    "Reseñas": details.get('user_ratings_total', 0),
                    "Google Maps": details.get('url', f"https://www.google.com/maps/place/?q=place_id:{place_id}")
                })
            
            # Si ya tenemos los resultados deseados, salimos
            if len(results) >= max_results:
                break
                
            # Si hay más páginas
            next_token = places_result.get('next_page_token')
            if not next_token:
                if console: console.write(f"⚠️ Se acabaron los resultados de Google Maps en esta zona.")
                break
                
            import time
            if console: console.write(f"🔄 Agotamos la página {pagina}. Esperando 2 segundos para saltar a la página {pagina+1} de Maps...")
            time.sleep(2) 
            places_result = gmaps.places(query=query, page_token=next_token)
            pagina += 1
            
        if console: console.update(label="✅ Extracción de Google Maps completada.", state="complete")
        return results
    except Exception as e:
        st.error(f"Error en Google Maps API: {e}")
        return []

def get_website_screenshot(url):
    """Obtiene una captura de pantalla de la URL usando la API gratuita de Microlink."""
    if url == 'No tiene':
        return None
    try:
        # Microlink API gratuita para tomar screenshot
        api_url = f"https://api.microlink.io?url={url}&screenshot=true&meta=false"
        response = requests.get(api_url)
        if response.status_code == 200:
            data = response.json()
            screenshot_url = data.get('data', {}).get('screenshot', {}).get('url')
            if screenshot_url:
                img_response = requests.get(screenshot_url)
                img = Image.open(BytesIO(img_response.content))
                return img
    except Exception as e:
        st.warning(f"No se pudo tomar captura de {url}: {e}")
    return None

def evaluate_website_and_write_email(img, website_url, business_name, gemini_key, custom_prompt_eval, custom_prompt_email):
    """Usa Gemini para evaluar la imagen y extraer datos clave para el scoring."""
    import json
    try:
        client = genai.Client(api_key=gemini_key)
        tokens_in = 0
        tokens_out = 0
        
        # 1. Evaluación Visual Estructurada
        # Forzamos a la IA a devolver un JSON con la evaluación y los checks de la matriz
        json_prompt = custom_prompt_eval + """
        \n\nIMPORTANTE: Debes responder ÚNICAMENTE con un objeto JSON válido con esta estructura exacta, sin texto extra (no uses markdown de código):
        {
            "aprobado": false,
            "razon": "breve razón aquí",
            "servicios_premium": true o false (si ves botox, láser, faciales premium, etc),
            "instagram_visible": true o false (si ves el logo o link de Instagram),
            "whatsapp_visible": true o false (si ves logo de WhatsApp o número visible),
            "agenda_visible": true o false (si ves botón de 'Agendar', 'Reservar cita')
        }
        """
        response_eval = client.models.generate_content(
            model='gemini-2.5-pro',
            contents=[img, json_prompt]
        )
        
        # Limpiar y parsear JSON
        raw_text = response_eval.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:-3].strip()
        
        try:
            datos_ia = json.loads(raw_text)
        except:
            datos_ia = {"aprobado": False, "razon": "Error al analizar imagen", "servicios_premium": False, "instagram_visible": False, "whatsapp_visible": False, "agenda_visible": False}

        evaluacion_texto = "APROBADO" if datos_ia.get("aprobado") else "RECHAZADO"
        evaluacion_completa = f"{evaluacion_texto} - {datos_ia.get('razon', '')}"

        if hasattr(response_eval, 'usage_metadata') and response_eval.usage_metadata:
            tokens_in += getattr(response_eval.usage_metadata, 'prompt_token_count', 0)
            tokens_out += getattr(response_eval.usage_metadata, 'candidates_token_count', 0)
            
        # AHORRO DE TOKENS: Si la web es buena, no necesitamos escribirle un correo para venderle otra.
        if datos_ia.get("aprobado"):
            return evaluacion_completa, "DESCARTADO - El cliente ya tiene una web de alta calidad.", tokens_in, tokens_out, datos_ia
        
        # 2. Generación del Correo (Solo si la web fue RECHAZADA)
        prompt_email = custom_prompt_email.replace("{business_name}", business_name).replace("{website_url}", website_url).replace("{evaluacion}", evaluacion_completa)

        
        response_email = client.models.generate_content(
            model='gemini-2.5-pro',
            contents=prompt_email
        )
        correo = response_email.text.strip()
        if hasattr(response_email, 'usage_metadata') and response_email.usage_metadata:
            tokens_in += getattr(response_email.usage_metadata, 'prompt_token_count', 0)
            tokens_out += getattr(response_email.usage_metadata, 'candidates_token_count', 0)
        
        return evaluacion_completa, correo, tokens_in, tokens_out, datos_ia
    except Exception as e:
        return f"Error en IA: {str(e)}", "No se pudo generar el correo.", 0, 0, {}

# --- INTERFAZ PRINCIPAL ---

if iniciar_btn:
    if not gmaps_api_key or not gemini_api_key:
        st.warning("⚠️ Por favor, ingresa tus API Keys en la pestaña de Configuración antes de continuar.")
    else:
        st.info(f"Iniciando Misión de Prospección: '{search_query}'...")
        
        with st.status("🤖 Conectando con Google Maps...", expanded=True) as console:
            leads = get_places(search_query, gmaps_api_key, max_results, min_rating, max_rating, solo_sin_web, console)
            
        if not leads:
            st.error("No se encontraron resultados o hubo un error con la API de Google Maps.")
        else:
            st.success(f"¡Se encontraron {len(leads)} prospectos!")
            
            # --- Métricas en tiempo real ---
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Limpiar contadores de sesión para nueva corrida
            st.session_state.total_tokens = 0
            st.session_state.costo_estimado = 0.0
            
            # Espacios vacíos para actualizar en vivo
            col1, col2 = st.columns(2)
            metric_tokens_live = col1.empty()
            metric_cost_live = col2.empty()
            
            resultados_finales = []
            
            for i, lead in enumerate(leads):
                status_text.text(f"Analizando prospecto {i+1}/{len(leads)}: {lead['Nombre']}...")
                
                evaluacion = "N/A"
                correo = "N/A"
                score = 0
                
                # --- LOGICA DE LEAD SCORING ---
                # 1. Confianza/Reseñas
                resenas = lead['Reseñas']
                if resenas >= 100: score += pts_resenas_altas
                elif resenas >= 30: score += pts_resenas_medias
                
                # 2. Confianza/Rating
                if lead['Rating'] >= 4.6: score += pts_rating_alto
                
                if lead['Website'] == 'No tiene':
                    evaluacion = "CLIENTE IDEAL - No tiene página web."
                    score += pts_no_web # No tiene web
                    
                    # Generar correo para quien no tiene web
                    try:
                        client = genai.Client(api_key=gemini_api_key)
                        prompt_no_web = prompt_noweb_input.replace("{business_name}", lead['Nombre'])
                        resp = client.models.generate_content(model='gemini-2.5-pro', contents=prompt_no_web)
                        correo = resp.text.strip()
                        if hasattr(resp, 'usage_metadata') and resp.usage_metadata:
                            st.session_state.total_tokens += getattr(resp.usage_metadata, 'prompt_token_count', 0)
                            st.session_state.total_tokens += getattr(resp.usage_metadata, 'candidates_token_count', 0)
                    except:
                        correo = "Error al generar."
                else:
                    status_text.text(f"Tomando captura web de {lead['Nombre']}...")
                    img = get_website_screenshot(lead['Website'])
                    
                    if img:
                        status_text.text(f"La IA está evaluando el diseño de {lead['Nombre']}...")
                        evaluacion, correo, t_in, t_out, datos_ia = evaluate_website_and_write_email(img, lead['Website'], lead['Nombre'], gemini_api_key, prompt_eval_input, prompt_email_input)
                        st.session_state.total_tokens += (t_in + t_out)
                        
                        # --- SCORING VISUAL (IA) ---
                        if datos_ia.get('aprobado') == False: score += pts_web_mala
                        if datos_ia.get('servicios_premium'): score += pts_premium
                        if datos_ia.get('instagram_visible'): score += pts_marketing
                        if datos_ia.get('whatsapp_visible'): score += pts_whatsapp
                        if datos_ia.get('agenda_visible'): score += pts_agenda
                        
                    else:
                        evaluacion = "ALERTA ROJA - Sitio web caído o dominio expirado."
                        score += 20  # Es la mejor oportunidad de venta
                        
                        # Generar correo de emergencia para dominio caído
                        try:
                            client = genai.Client(api_key=gemini_api_key)
                            prompt_caido = prompt_caido_input.replace("{business_name}", lead['Nombre']).replace("{website_url}", lead['Website'])
                            resp = client.models.generate_content(model='gemini-2.5-pro', contents=prompt_caido)
                            correo = resp.text.strip()
                            if hasattr(resp, 'usage_metadata') and resp.usage_metadata:
                                st.session_state.total_tokens += getattr(resp.usage_metadata, 'prompt_token_count', 0)
                                st.session_state.total_tokens += getattr(resp.usage_metadata, 'candidates_token_count', 0)
                        except:
                            correo = "Error al generar correo de dominio caído."
                
                # Guardar resultado
                lead_data = {
                    "Score": score,
                    "Negocio": lead['Nombre'],
                    "Rating": lead['Rating'],
                    "Reseñas": lead['Reseñas'],
                    "Website": lead['Website'],
                    "Teléfono": lead['Teléfono'],
                    "Link Maps": lead['Google Maps'],
                    "Diagnóstico IA": evaluacion,
                    "Correo Generado": correo
                }
                resultados_finales.append(lead_data)
                
                # Actualizar Métricas en tiempo real
                status_text.text(f"Analizando prospecto {i+1}/{len(leads)}: {lead['Nombre']}...")
                metric_tokens_live.metric("Tokens Usados (En vivo)", f"{st.session_state.total_tokens:,}")
                
                # Costo estimado Gemini 1.5 Pro ($1.25 / 1M prompt, $3.75 / 1M completion)
                # Para simplificar el vivo, usamos un promedio de $2.50 por 1M tokens totales
                st.session_state.costo_estimado = (st.session_state.total_tokens / 1_000_000) * 2.50
                metric_cost_live.metric("Costo Estimado (USD)", f"${st.session_state.costo_estimado:.4f}")
                
                progress_bar.progress((i + 1) / len(leads))
                time.sleep(1) # Pequeña pausa para no saturar APIs
                
            status_text.text("¡Prospección completada! 🎉")
            
            # Guardar costo en el histórico
            if st.session_state.costo_estimado > 0:
                agregar_costo_historico(st.session_state.costo_estimado)
            
            # Guardar en la memoria de la sesión
            st.session_state.resultados = pd.DataFrame(resultados_finales)

# --- MOSTRAR RESULTADOS GUARDADOS ---
if st.session_state.resultados is not None:
    st.markdown("---")
    st.markdown("### 📊 Resultados de tu Prospección")
    
    # Mostrar métricas guardadas de forma permanente
    col1, col2 = st.columns(2)
    col1.metric("Total Tokens Usados", f"{st.session_state.total_tokens:,}")
    col2.metric("Costo Final (USD)", f"${st.session_state.costo_estimado:.4f}")
    
    st.dataframe(st.session_state.resultados)
    
    # Botón de Descarga Excel
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        st.session_state.resultados.to_excel(writer, index=False, sheet_name='Leads')
    
    excel_data = output.getvalue()
    
    # Crear nombre dinámico para el archivo Excel
    import datetime
    import re
    # Limpiar la búsqueda para que sea un nombre de archivo válido
    safe_query = re.sub(r'[^a-zA-Z0-9]', '_', search_query)
    # Evitar múltiples guiones bajos seguidos
    safe_query = re.sub(r'_+', '_', safe_query).strip('_')
    today_str = datetime.date.today().strftime('%Y-%m-%d')
    dynamic_filename = f"leads_{safe_query}_{today_str}.xlsx"
    
    # Botón de Descarga Excel centrado
    st.markdown("<br>", unsafe_allow_html=True)
    col_dl1, col_dl2, col_dl3 = st.columns([1,2,1])
    with col_dl2:
        st.download_button(
            label="📥 Descargar Leads en Excel (.xlsx)",
            data=excel_data,
            file_name=dynamic_filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

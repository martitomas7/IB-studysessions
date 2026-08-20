// IndicadorLaboratorioMercado.cs · D-C (Rama B) · 08_LABORATORIO.md §1.1
// ============================================================================
// AVISO DE CONFIANZA (mismo principio que 07_ADAPTADOR_NT8.md §3 y
// da1_diagnostico.ps1): este fichero se ha escrito y revisado a mano contra
// la documentación pública de NinjaScript, pero NO se ha compilado ni
// ejecutado contra NT8 real -- este entorno de ingeniería es Linux, sin NT8.
// Cuando el operador lo compile por primera vez en NinjaTrader (F5 en el
// editor de NinjaScript), CUALQUIER error de compilación es una comprobación
// más que hay que ver fallar antes de darse por buena (R3): pégalo tal cual,
// se corrige de inmediato. Puntos concretos sin verificar, marcados abajo con
// "// SIN VERIFICAR": el nombre exacto del evento de datos de mercado
// (OnMarketData vs. una alternativa), y el cálculo de "día de negociación".
//
// REGLAS QUE ESTE FICHERO CUMPLE A PROPÓSITO (08_LABORATORIO.md §1.1):
//   - SOLO ESCRIBE. Ningún "if" de este fichero decide nada de negocio --
//     el único condicional de valor es "¿cambió bid/ask/last?".
//   - Cabe en una pantalla.
//   - No bloquea a NT8: acumula líneas en memoria y las vuelca cada
//     `INTERVALO_VOLCADO_S` segundos -- NUNCA hace flush por tick.
//   - Ninguna operación de red ni de interfaz.
// ============================================================================
using System;
using System.IO;
using System.Text;
using NinjaTrader.NinjaScript.Indicators;

namespace NinjaTrader.NinjaScript.Indicators
{
    public class IndicadorLaboratorioMercado : Indicator
    {
        private const int INTERVALO_VOLCADO_S = 5;   // ingeniería, no negocio -- ver 08_LABORATORIO.md §2
        private StringBuilder buffer = new StringBuilder();
        private DateTime ultimoVolcado = DateTime.MinValue;
        private double ultimoBid = double.NaN, ultimoAsk = double.NaN, ultimoLast = double.NaN;
        private int diaNegociacionActual = -1;
        private string rutaSalida;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "D-C / 08_LABORATORIO.md §1.1 -- vuelca bid/ask/last a laboratorio/mercado_<dia>.jsonl. Solo escribe, no decide.";
                Name = "IndicadorLaboratorioMercado";
                Calculate = Calculate.OnEachTick;   // SIN VERIFICAR: necesario para granularidad de tick real
                IsOverlay = true;                    // no dibuja nada -- ver OnRender ausente a propósito
            }
            else if (State == State.Realtime)
            {
                ultimoVolcado = DateTime.Now;
            }
            else if (State == State.Terminated)
            {
                VolcarBuffer(forzar: true);
            }
        }

        // SIN VERIFICAR: la firma exacta de este evento (nombre, argumentos) no
        // está confirmada contra la DLL real -- si NT8 la rechaza al compilar,
        // es la comprobación que D-A1.1 ya avisa que puede hacer falta: revisar
        // el volcado por reflexión de da1_diagnostico.ps1 para el nombre real.
        protected override void OnMarketData(NinjaTrader.Data.MarketDataEventArgs e)
        {
            double bid = GetCurrentBid(), ask = GetCurrentAsk(), last = Close[0];
            if (bid == ultimoBid && ask == ultimoAsk && last == ultimoLast)
                return;   // "¿cambió el valor?" -- el ÚNICO condicional de negocio permitido
            ultimoBid = bid; ultimoAsk = ask; ultimoLast = last;

            // SIN VERIFICAR: rotación por "día de negociación" -- se aproxima con
            // la fecha de la sesión de Bars; 08_LABORATORIO.md §2 exige que NO sea
            // medianoche de reloj (la sesión de 22h la cruza). Ajustar contra el
            // calendario real de sesión cuando se compile por primera vez.
            int diaHoy = Bars != null ? Bars.GetTradingDayOfWeek(Time[0]).GetHashCode() : 0; // placeholder, ver aviso
            string tsPared = DateTime.Now.ToString("o");
            double tsMonotono = (DateTime.Now - System.Diagnostics.Process.GetCurrentProcess().StartTime).TotalSeconds;
            string linea = string.Format(
                "{{\"ts_pared\":\"{0}\",\"ts_monotono\":{1:F3},\"instrumento\":\"{2}\",\"bid\":{3},\"ask\":{4},\"last\":{5},\"estado_feed\":\"DESCONOCIDO\"}}",
                tsPared, tsMonotono, Instrument.FullName, bid, ask, last);
            // estado_feed="DESCONOCIDO" a propósito: NinjaScript no expone de forma
            // documentada si el feed es tiempo-real o retrasado (08_LABORATORIO.md
            // §1.1: DESCONOCIDO se trata como RETRASADO -- nunca tiempo real por
            // defecto). Confirmar a mano en NT8 (Control Center -> Connections) y
            // anotar en 08_LABORATORIO.md la primera vez que se corra.
            buffer.AppendLine(linea);

            if ((DateTime.Now - ultimoVolcado).TotalSeconds >= INTERVALO_VOLCADO_S)
                VolcarBuffer(forzar: false);
        }

        private void VolcarBuffer(bool forzar)
        {
            if (buffer.Length == 0) return;
            try
            {
                if (rutaSalida == null)
                    rutaSalida = Path.Combine(NinjaTrader.Core.Globals.UserDataDir, "laboratorio",
                                               "mercado_indicador.jsonl");  // rotación real: ver aviso arriba
                Directory.CreateDirectory(Path.GetDirectoryName(rutaSalida));
                File.AppendAllText(rutaSalida, buffer.ToString());
                buffer.Clear();
                ultimoVolcado = DateTime.Now;
            }
            catch (Exception) { /* solo escribe -- un fallo de disco no debe tirar NT8 abajo */ }
        }
    }
}

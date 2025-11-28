<?php
/**
 * Plugin Name: Gaia Eyes – Spark Helper
 * Description: Shared helper for sparkline charts with labeled axes and graceful fallbacks.
 * Version: 1.0.0
 */

if (!defined('ABSPATH')) {
  exit;
}

if (!function_exists('gaiaeyes_output_spark_helper')) {
  function gaiaeyes_output_spark_helper() {
    static $printed = false;
    if ($printed || is_admin()) {
      return;
    }
    $printed = true;
    ?>
    <script>
      (function(window){
        if (window.GaiaSpark && window.GaiaSpark.renderSpark) {
          return;
        }
        const charts = new WeakMap();

        function resolveCanvas(target){
          if (!target) return null;
          if (typeof target === 'string') return document.getElementById(target);
          return target;
        }

        function normalisePoint(pt, index){
          if (pt == null) return null;
          if (typeof pt === 'number') {
            return { x: index, y: pt };
          }
          if (Array.isArray(pt)) {
            const x = pt.length > 1 ? pt[0] : index;
            const y = pt.length > 1 ? pt[1] : pt[0];
            return { x: x ?? index, y };
          }
          if (typeof pt === 'object') {
            const x = pt.x ?? pt.time ?? pt.timestamp ?? pt.t ?? pt[0] ?? index;
            const y = pt.y ?? pt.value ?? pt.v ?? pt.val ?? pt.kp ?? pt[1];
            return (x == null || y == null) ? null : { x, y };
          }
          return null;
        }

        function prepareData(data){
          if (!Array.isArray(data)) return [];
          const out = [];
          data.forEach((pt, idx) => {
            const norm = normalisePoint(pt, idx);
            if (!norm) return;
            let x = norm.x;
            if (typeof x === 'string') {
              const d = new Date(x);
              if (!isNaN(+d)) {
                x = d;
              }
            } else if (typeof x === 'number' && isFinite(x) && x > 1e11) {
              const d = new Date(x);
              if (!isNaN(+d)) {
                x = d;
              }
            }
            const y = Number(norm.y);
            if (!isFinite(y)) return;
            out.push({ x, y });
          });
          return out;
        }

        function ensureSize(canvas){
          const parent = canvas.parentElement;
          if (!parent) return;
          const w = parent.clientWidth || canvas.width || 320;
          const h = parent.clientHeight || canvas.height || 120;
          canvas.width = w;
          canvas.height = h;
        }

        function clearCanvas(canvas){
          const ctx = canvas.getContext('2d');
          if (ctx) ctx.clearRect(0, 0, canvas.width || 0, canvas.height || 0);
        }

        function buildYTitle(yLabel, units){
          if (yLabel && units) return yLabel + ' (' + units + ')';
          if (yLabel) return yLabel;
          if (units) return '(' + units + ')';
          return '';
        }

        window.GaiaSpark = {
          renderSpark(target, data, options){
            const canvas = resolveCanvas(target);
            if (!canvas) return null;
            const ChartLib = window.Chart;
            if (!ChartLib || typeof ChartLib !== 'function') {
              console.warn('GaiaSpark: Chart.js must be loaded before rendering sparklines.');
              return null;
            }
            const cfg = Object.assign({
              xLabel: 'Time',
              yLabel: '',
              units: '',
              yMin: undefined,
              yMax: undefined,
              color: '#7fc8ff',
              zeroLine: false,
              tension: 0.25,
              fontSize: 11,
              backgroundColor: '#151a24'
            }, options || {});

            const dataset = prepareData(data);
            const existing = charts.get(canvas);
            if (existing) {
              existing.destroy();
              charts.delete(canvas);
            }
            if (!dataset.length) {
              canvas.setAttribute('data-gaia-spark-empty', '1');
              clearCanvas(canvas);
              return null;
            }
            canvas.removeAttribute('data-gaia-spark-empty');
            ensureSize(canvas);

            const usesDates = dataset[0].x instanceof Date;
            const yTitle = buildYTitle(cfg.yLabel, cfg.units);

            const scales = {
              x: {
                type: usesDates ? 'time' : 'linear',
                grid: { display: true, color: 'rgba(233, 238, 247, 0.12)' },
                border: { display: true, color: 'rgba(233, 238, 247, 0.24)' },
                ticks: {
                  color: 'rgba(233, 238, 247, 0.9)',
                  font: { size: Math.max(10, cfg.fontSize) },
                  maxTicksLimit: 6
                },
                title: {
                  display: !!cfg.xLabel,
                  text: cfg.xLabel,
                  color: 'rgba(233, 238, 247, 0.95)',
                  font: { size: Math.max(11, cfg.fontSize + 1) }
                }
              },
              y: {
                grid: { display: true, color: 'rgba(233, 238, 247, 0.12)' },
                border: { display: true, color: 'rgba(233, 238, 247, 0.24)' },
                ticks: {
                  color: 'rgba(233, 238, 247, 0.9)',
                  font: { size: Math.max(10, cfg.fontSize) },
                  padding: 6
                },
                title: {
                  display: !!yTitle,
                  text: yTitle,
                  color: 'rgba(233, 238, 247, 0.95)',
                  font: { size: Math.max(11, cfg.fontSize + 1) }
                }
              }
            };

            if (cfg.yMin !== undefined) {
              scales.y.min = cfg.yMin;
            }
            if (cfg.yMax !== undefined) {
              scales.y.max = cfg.yMax;
            }

            const backgroundPlugin = {
              id: 'gaiaSparkBackground',
              beforeDraw(chart){
                const {ctx, chartArea} = chart;
                if (!chartArea) return;
                ctx.save();
                ctx.fillStyle = cfg.backgroundColor || '#151a24';
                ctx.fillRect(chartArea.left, chartArea.top, chartArea.right - chartArea.left, chartArea.bottom - chartArea.top);
                ctx.restore();
              }
            };

            const zeroLinePlugin = {
              id: 'gaiaSparkZero',
              afterDraw(chart){
                if (!cfg.zeroLine) return;
                const yScale = chart.scales && chart.scales.y;
                if (!yScale) return;
                const yZero = yScale.getPixelForValue(0);
                const ctx = chart.ctx;
                ctx.save();
                ctx.setLineDash([4, 4]);
                ctx.strokeStyle = 'rgba(233, 238, 247, 0.45)';
                ctx.beginPath();
                ctx.moveTo(chart.chartArea.left, yZero);
                ctx.lineTo(chart.chartArea.right, yZero);
                ctx.stroke();
                ctx.restore();
              }
            };

            const chart = new ChartLib(canvas.getContext('2d'), {
              type: 'line',
              data: {
                datasets: [{
                  data: dataset,
                  borderColor: cfg.color,
                  borderWidth: 1.8,
                  tension: cfg.tension,
                  pointRadius: 0,
                  fill: false
                }]
              },
              options: {
                parsing: false,
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                layout: { padding: { top: 16, right: 18, bottom: 30, left: 36 } },
                scales: scales,
                plugins: {
                  legend: { display: false },
                  tooltip: { enabled: false }
                }
              },
              plugins: [backgroundPlugin, zeroLinePlugin]
            });

            charts.set(canvas, chart);
            return chart;
          }
        };

        window.dispatchEvent(new CustomEvent('gaiaSparkReady', { detail: window.GaiaSpark }));
      })(window);
    </script>
    <?php
  }
  add_action('wp_footer', 'gaiaeyes_output_spark_helper', 1);
}

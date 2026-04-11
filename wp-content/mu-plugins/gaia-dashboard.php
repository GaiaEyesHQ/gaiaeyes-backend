<?php
/*
Plugin Name: Gaia Dashboard Shortcode
Description: Renders the member dashboard from /v1/dashboard via Supabase session auth.
Version: 0.1.0
*/

if (!defined('ABSPATH')) {
    exit;
}

add_action('wp_enqueue_scripts', function () {
    wp_register_script(
        'gaia-dashboard',
        plugins_url('gaia-dashboard.js', __FILE__),
        ['supabase-js'],
        filemtime(__DIR__ . '/gaia-dashboard.js'),
        true
    );

    $supabase_url = defined('SUPABASE_URL') ? SUPABASE_URL : getenv('SUPABASE_URL');
    $supabase_anon = defined('SUPABASE_ANON_KEY') ? SUPABASE_ANON_KEY : getenv('SUPABASE_ANON_KEY');
    $backend_base = defined('GAIAEYES_API_BASE') ? GAIAEYES_API_BASE : getenv('GAIAEYES_API_BASE');
    $media_base = defined('MEDIA_BASE_URL') ? MEDIA_BASE_URL : getenv('MEDIA_BASE_URL');
    $symptom_log_url = apply_filters('gaia_dashboard_symptom_log_url', home_url('/symptoms/'));
    if (!$media_base && $supabase_url) {
        $media_base = rtrim($supabase_url, '/') . '/storage/v1/object/public/space-visuals';
    }
    $request_uri = isset($_SERVER['REQUEST_URI']) ? wp_unslash($_SERVER['REQUEST_URI']) : '/';
    $redirect_url = esc_url_raw(home_url($request_uri));
    $member_routes = [
        'dashboard' => esc_url_raw(rest_url('gaia/v1/dashboard')),
        'drivers' => esc_url_raw(rest_url('gaia/v1/member/drivers')),
        'outlook' => esc_url_raw(rest_url('gaia/v1/member/outlook')),
        'patternsSummary' => esc_url_raw(rest_url('gaia/v1/member/patterns-summary')),
        'patterns' => esc_url_raw(rest_url('gaia/v1/member/patterns')),
        'features' => esc_url_raw(rest_url('gaia/v1/member/features')),
        'symptomCodes' => esc_url_raw(rest_url('gaia/v1/member/symptom-codes')),
        'symptomLog' => esc_url_raw(rest_url('gaia/v1/member/symptoms')),
        'currentSymptoms' => esc_url_raw(rest_url('gaia/v1/member/current-symptoms')),
        'currentSymptomUpdatesBase' => esc_url_raw(rest_url('gaia/v1/member/current-symptoms')),
        'followUpBase' => esc_url_raw(rest_url('gaia/v1/member/follow-ups')),
        'dailyCheckIn' => esc_url_raw(rest_url('gaia/v1/member/daily-checkin')),
        'lunar' => esc_url_raw(rest_url('gaia/v1/member/lunar')),
        'localCheck' => esc_url_raw(rest_url('gaia/v1/member/local-check')),
        'profilePreferences' => esc_url_raw(rest_url('gaia/v1/member/profile-preferences')),
        'guideSeen' => esc_url_raw(rest_url('gaia/v1/member/guide-seen')),
        'notifications' => esc_url_raw(rest_url('gaia/v1/member/notifications')),
        'accountPreflight' => esc_url_raw(rest_url('gaia/v1/member/account/preflight')),
        'accountDelete' => esc_url_raw(rest_url('gaia/v1/member/account')),
    ];

    wp_localize_script('gaia-dashboard', 'GAIA_DASHBOARD_CFG', [
        'supabaseUrl' => $supabase_url ? rtrim($supabase_url, '/') : '',
        'supabaseAnon' => $supabase_anon ? trim($supabase_anon) : '',
        'backendBase' => $backend_base ? rtrim($backend_base, '/') : '',
        'dashboardProxy' => esc_url_raw(rest_url('gaia/v1/dashboard')),
        'memberRoutes' => $member_routes,
        'mediaBase' => $media_base ? rtrim($media_base, '/') : '',
        'redirectUrl' => $redirect_url,
        'symptomLogUrl' => $symptom_log_url ? esc_url_raw($symptom_log_url) : '',
        'supportUrl' => esc_url_raw(home_url('/support/')),
        'privacyUrl' => esc_url_raw(home_url('/privacy/')),
        'termsUrl' => esc_url_raw(home_url('/terms/')),
        'publicLinks' => [
            'spaceWeather' => esc_url_raw(home_url('/space-weather/')),
            'schumann' => esc_url_raw(home_url('/schumann-resonance/')),
            'magnetosphere' => esc_url_raw(home_url('/magnetosphere/')),
            'aurora' => esc_url_raw(home_url('/aurora-tracker/')),
            'earthquakes' => esc_url_raw(home_url('/earthquakes/')),
        ],
    ]);

    wp_register_style('gaia-dashboard', false);
    wp_add_inline_style('gaia-dashboard', '
        .gaia-dashboard{border:1px solid rgba(255,255,255,.08);border-radius:14px;padding:16px;background:#0f131a;color:#e8edf7}
        .gaia-dashboard__muted{color:#9da9c1;font-size:13px}
        .gaia-dashboard__status{color:#9da9c1}
        .gaia-dashboard__head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}
        .gaia-dashboard__title{font-size:22px;font-weight:700;line-height:1.2;margin:0}
        .gaia-dashboard__mode{font-size:12px;padding:3px 8px;border-radius:999px;background:#1f2a3a;color:#9cc0ff}
        .gaia-dashboard__gauges{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin:12px 0;align-items:stretch}
        @media(min-width:900px){.gaia-dashboard__gauges{grid-template-columns:repeat(3,minmax(0,1fr));}}
        @media(min-width:1200px){.gaia-dashboard__gauges{grid-template-columns:repeat(4,minmax(0,1fr));}}
        .gaia-dashboard__gauge{padding:12px;border-radius:14px;background:#151c28;display:flex;flex-direction:column;gap:10px;min-height:150px}
        .gaia-dashboard__gauge--clickable{cursor:pointer;transition:transform .15s ease,box-shadow .15s ease,border-color .15s ease;border:1px solid rgba(255,255,255,.16)}
        .gaia-dashboard__gauge--clickable:hover{transform:translateY(-1px);box-shadow:0 0 16px rgba(162,186,223,.22);border-color:rgba(162,186,223,.42)}
        .gaia-dashboard__gauge-label{font-size:15px;font-weight:650;color:#eef4ff;line-height:1.25}
        .gaia-dashboard__gauge-meter{position:relative;display:grid;place-items:center;margin-top:2px}
        .gaia-dashboard__gauge-arc{width:104px;height:104px;display:block}
        @media(min-width:1200px){.gaia-dashboard__gauge-arc{width:110px;height:110px}}
        .gaia-dashboard__gauge-ring{fill:none;stroke:rgba(255,255,255,.12);stroke-width:9}
        .gaia-dashboard__gauge-value-arc{fill:none;stroke-width:9;stroke-linecap:round}
        .gaia-dashboard__gauge-center{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;pointer-events:none}
        .gaia-dashboard__gauge-value{font-size:26px;font-weight:750;line-height:1;display:flex;gap:4px;align-items:baseline}
        .gaia-dashboard__gauge-delta{font-size:12px;font-weight:600;color:#8f9db7}
        .gaia-dashboard__gauge-delta--strong{color:#d8b176}
        .gaia-dashboard__gauge-zone{font-size:12px;line-height:1.2;opacity:.95}
        .gaia-dashboard__gauge-zone-key{font-size:11px;color:#9da9c1;text-align:center;margin-top:2px}
        .gaia-dashboard__gauge-dot{fill:#fff;stroke:#1a2434;stroke-width:1.6}
        .gaia-dashboard__tap-hint{font-size:10px;color:#c6d3ea;letter-spacing:.02em}
        .gaia-dashboard__gauge-legend{display:flex;flex-wrap:wrap;gap:10px;margin:4px 0 10px}
        .gaia-dashboard__legend-item{display:inline-flex;align-items:center;gap:6px;font-size:11px;color:#9da9c1}
        .gaia-dashboard__legend-dot{width:8px;height:8px;border-radius:50%}
        .gaia-dashboard__alerts{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}
        .gaia-dashboard__pill{padding:5px 10px;border-radius:999px;font-size:12px;background:#223246;color:#a9c8ff}
        .gaia-dashboard__pill--watch{background:#3a2d19;color:#ffd58f}
        .gaia-dashboard__pill--high{background:#3b1e23;color:#ffadb8}
        .gaia-dashboard__drivers{margin-top:12px;padding:12px;border-radius:12px;background:#131b28}
        .gaia-dashboard__drivers h4{margin:0 0 10px;font-size:17px}
        .gaia-dashboard__driver-group{display:flex;flex-direction:column;gap:8px}
        .gaia-dashboard__driver-group + .gaia-dashboard__driver-group{margin-top:12px}
        .gaia-dashboard__driver-section-head h5{margin:0;font-size:12px;text-transform:none;color:#eef4ff}
        .gaia-dashboard__driver-section-head p{margin:3px 0 0;font-size:11px;color:#9da9c1;line-height:1.4}
        .gaia-dashboard__drivers-list{display:flex;flex-direction:column;gap:9px}
        .gaia-dashboard__driver-row{padding:10px;border-radius:12px;background:#172130;border:1px solid rgba(255,255,255,.08)}
        .gaia-dashboard__driver-row--leading{background:rgba(51,68,92,.78);border-color:rgba(211,167,108,.56);box-shadow:0 0 18px rgba(211,167,108,.18)}
        .gaia-dashboard__driver-row--supporting{border-color:rgba(255,255,255,.12)}
        .gaia-dashboard__driver-row--background{background:#141c28;border-color:rgba(255,255,255,.05);opacity:.9}
        .gaia-dashboard__driver-row--clickable{cursor:pointer;transition:box-shadow .15s ease,border-color .15s ease}
        .gaia-dashboard__driver-row--clickable:hover{box-shadow:0 0 14px rgba(163,188,225,.18);border-color:rgba(163,188,225,.36)}
        .gaia-dashboard__driver-head{display:flex;align-items:flex-start;gap:10px;justify-content:space-between}
        .gaia-dashboard__driver-copy{display:flex;flex-direction:column;gap:4px;min-width:0}
        .gaia-dashboard__driver-meta{display:flex;align-items:baseline;gap:8px;justify-content:flex-end;flex-wrap:wrap}
        .gaia-dashboard__driver-label{font-size:14px;font-weight:650}
        .gaia-dashboard__driver-reason{font-size:12px;color:#9da9c1;line-height:1.45}
        .gaia-dashboard__driver-state{font-size:12px}
        .gaia-dashboard__driver-value{font-size:12px;color:#9da9c1}
        .gaia-dashboard__driver-bar-track{margin-top:8px;height:9px;border-radius:999px;background:rgba(255,255,255,.09);overflow:hidden}
        .gaia-dashboard__driver-bar-fill{height:100%;border-radius:999px}
        .gaia-dashboard__geomag{margin-top:12px;padding:12px;border-radius:12px;background:#151c28;border:1px solid rgba(255,255,255,.08)}
        .gaia-dashboard__geomag-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}
        .gaia-dashboard__geomag h4{margin:0 0 6px;font-size:17px}
        .gaia-dashboard__geomag-summary{margin:0;color:#e8edf7;font-size:14px;line-height:1.45}
        .gaia-dashboard__geomag-meta{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
        .gaia-dashboard__geomag-chip{display:inline-flex;align-items:center;padding:5px 10px;border-radius:999px;background:#1c2636;color:#c6d3ea;font-size:12px}
        .gaia-dashboard__earthscope{margin-top:12px;padding:12px;border-radius:12px;background:#151c28}
        .gaia-dashboard__earthscope h4{margin:0 0 8px;font-size:18px}
        .gaia-dashboard__earthscope-preview{display:flex;flex-direction:column;gap:8px}
        .gaia-dashboard__earthscope-row{padding:10px;border-radius:10px;background:rgba(0,0,0,.18)}
        .gaia-dashboard__earthscope-label{font-size:11px;font-weight:700;color:#9da9c1;margin-bottom:3px}
        .gaia-dashboard__earthscope-copy{font-size:14px;line-height:1.5;color:#e8edf7}
        .gaia-dashboard__earthscope-summary{font-size:14px;line-height:1.5;margin:0 0 10px;color:#e8edf7}
        .gaia-dashboard__earthscope-link{display:inline-flex;align-items:center;font-size:13px;color:#9cc0ff;text-decoration:underline;background:none;border:0;padding:0;cursor:pointer}
        .gaia-dashboard__es-grid{display:grid;grid-template-columns:1fr;gap:10px}
        @media(min-width:900px){.gaia-dashboard__es-grid{grid-template-columns:1fr 1fr}}
        .gaia-dashboard__es-block{position:relative;overflow:hidden;border-radius:12px;min-height:150px;background:#0f1a2b;background-size:cover;background-position:center}
        .gaia-dashboard__es-overlay{position:absolute;inset:0;background:linear-gradient(to bottom,rgba(0,0,0,.32),rgba(0,0,0,.72))}
        .gaia-dashboard__es-content{position:relative;z-index:1;padding:12px;color:#fff}
        .gaia-dashboard__es-title{margin:0 0 8px;font-size:15px;line-height:1.25}
        .gaia-dashboard__es-body{margin:0;white-space:pre-line;line-height:1.45;font-size:14px}
        .gaia-dashboard__signin{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
        .gaia-dashboard__btn{border:0;border-radius:999px;padding:8px 14px;background:#2b8cff;color:#fff;font-weight:600;cursor:pointer}
        .gaia-dashboard__btn--ghost{background:#1f2a3a;color:#d7e6ff}
        .gaia-dashboard__btn--quiet{background:#172130;color:#d7e6ff;border:1px solid rgba(255,255,255,.08)}
        .gaia-dashboard__btn--danger{background:rgba(187,92,97,.16);color:#ffd5d8;border:1px solid rgba(230,122,126,.32)}
        .gaia-dashboard__shell{display:flex;flex-direction:column;gap:14px}
        .gaia-dashboard__shell-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap}
        .gaia-dashboard__shell-copy{display:flex;flex-direction:column;gap:4px;max-width:760px}
        .gaia-dashboard__shell-kicker{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#9da9c1}
        .gaia-dashboard__shell-subtitle{font-size:14px;line-height:1.5;color:#c7d3eb;margin:0}
        .gaia-dashboard__section{display:none;flex-direction:column;gap:14px}
        .gaia-dashboard__section.is-active{display:flex}
        .gaia-dashboard__section-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap}
        .gaia-dashboard__section-copy{display:flex;flex-direction:column;gap:4px}
        .gaia-dashboard__section-title{margin:0;font-size:24px;line-height:1.15}
        .gaia-dashboard__section-subtitle{margin:0;font-size:14px;line-height:1.5;color:#9da9c1;max-width:760px}
        .gaia-dashboard__nav-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
        @media(min-width:900px){.gaia-dashboard__nav-grid{grid-template-columns:repeat(auto-fit,minmax(160px,1fr));}}
        .gaia-dashboard__nav-grid--hub{margin-top:2px}
        .gaia-dashboard__nav-card{padding:14px;border-radius:14px;background:#151c28;border:1px solid rgba(255,255,255,.08);cursor:pointer;text-align:left;color:#e8edf7;position:relative}
        .gaia-dashboard__nav-card.is-active{background:#1e314c;border-color:rgba(156,192,255,.38);box-shadow:0 0 0 1px rgba(156,192,255,.12) inset}
        .gaia-dashboard__nav-card--unseen{border-color:rgba(84,201,255,.34);box-shadow:0 0 0 1px rgba(84,201,255,.10) inset,0 0 18px rgba(84,201,255,.14)}
        .gaia-dashboard__nav-card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}
        .gaia-dashboard__nav-card strong{display:block;font-size:14px}
        .gaia-dashboard__nav-card span{display:block;margin-top:5px;font-size:12px;color:#9da9c1;line-height:1.45}
        .gaia-dashboard__nav-badge{display:inline-flex;align-items:center;justify-content:center;padding:4px 9px;border-radius:999px;background:rgba(43,140,255,.16);border:1px solid rgba(84,201,255,.28);color:#8fdcff;font-size:11px;font-weight:700;letter-spacing:.03em;white-space:nowrap}
        .gaia-dashboard__sticky-tabs{position:sticky;top:12px;z-index:80;padding:10px;border-radius:20px;background:rgba(10,14,22,.88);border:1px solid rgba(255,255,255,.1);box-shadow:0 18px 40px rgba(0,0,0,.28);backdrop-filter:blur(16px)}
        body.admin-bar .gaia-dashboard__sticky-tabs{top:46px}
        .gaia-dashboard__sticky-tabs-scroll{display:flex;gap:8px;overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:none}
        .gaia-dashboard__sticky-tabs-scroll::-webkit-scrollbar{display:none}
        .gaia-dashboard__sticky-tab{position:relative;display:inline-flex;align-items:center;justify-content:center;gap:6px;min-height:38px;padding:8px 12px;border-radius:999px;border:1px solid rgba(255,255,255,.08);background:#151c28;color:#dfe9fb;cursor:pointer;white-space:nowrap;font-size:12px;font-weight:750;letter-spacing:.01em;flex:0 0 auto}
        .gaia-dashboard__sticky-tab.is-active{background:#1e314c;border-color:rgba(156,192,255,.4);box-shadow:0 0 0 1px rgba(156,192,255,.12) inset}
        .gaia-dashboard__sticky-tab--unseen{border-color:rgba(84,201,255,.32)}
        .gaia-dashboard__sticky-tab-dot{width:7px;height:7px;border-radius:999px;background:#59d1ff;box-shadow:0 0 10px rgba(89,209,255,.45)}
        .gaia-dashboard__mobile-tabbar{display:none}
        .gaia-dashboard__mobile-tabbar-scroll{display:flex;gap:8px;overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:none}
        .gaia-dashboard__mobile-tabbar-scroll::-webkit-scrollbar{display:none}
        .gaia-dashboard__mobile-tab{position:relative;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;min-width:68px;padding:10px 12px;border-radius:16px;border:1px solid rgba(255,255,255,.08);background:#151c28;color:#dfe9fb;cursor:pointer;flex:0 0 auto}
        .gaia-dashboard__mobile-tab.is-active{background:#1e314c;border-color:rgba(156,192,255,.38);box-shadow:0 0 0 1px rgba(156,192,255,.12) inset}
        .gaia-dashboard__mobile-tab--unseen{border-color:rgba(84,201,255,.28)}
        .gaia-dashboard__mobile-tab-icon{font-size:16px;line-height:1}
        .gaia-dashboard__mobile-tab-label{font-size:11px;font-weight:700;line-height:1.1;white-space:nowrap}
        .gaia-dashboard__mobile-tab-dot{position:absolute;top:8px;right:10px;width:7px;height:7px;border-radius:999px;background:#59d1ff;box-shadow:0 0 10px rgba(89,209,255,.45)}
        .gaia-dashboard__grid{display:grid;grid-template-columns:1fr;gap:14px}
        @media(min-width:900px){.gaia-dashboard__grid--2{grid-template-columns:repeat(2,minmax(0,1fr));}}
        @media(min-width:1200px){.gaia-dashboard__grid--3{grid-template-columns:repeat(3,minmax(0,1fr));}}
        .gaia-dashboard__card{padding:16px;border-radius:16px;background:#141b27;border:1px solid rgba(255,255,255,.08);display:flex;flex-direction:column;gap:12px}
        .gaia-dashboard__card-title-row{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}
        .gaia-dashboard__card-title{margin:0;font-size:18px;line-height:1.2}
        .gaia-dashboard__card-copy{margin:0;font-size:14px;line-height:1.55;color:#c9d4e8}
        .gaia-dashboard__eyebrow{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:#8f9db7}
        .gaia-dashboard__meta-row{display:flex;flex-wrap:wrap;gap:8px}
        .gaia-dashboard__meta-chip{display:inline-flex;align-items:center;gap:6px;padding:6px 10px;border-radius:999px;background:#1a2434;color:#d6e3fa;font-size:12px}
        .gaia-dashboard__metric-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
        @media(min-width:1100px){.gaia-dashboard__metric-grid--4{grid-template-columns:repeat(4,minmax(0,1fr));}}
        @media(min-width:1100px){.gaia-dashboard__metric-grid--3{grid-template-columns:repeat(3,minmax(0,1fr));}}
        .gaia-dashboard__metric{padding:12px;border-radius:12px;background:#172130;border:1px solid rgba(255,255,255,.08)}
        .gaia-dashboard__metric-label{font-size:11px;color:#8f9db7;text-transform:uppercase;letter-spacing:.06em}
        .gaia-dashboard__metric-value{font-size:20px;font-weight:700;margin-top:4px}
        .gaia-dashboard__metric-detail{font-size:12px;color:#9da9c1;margin-top:4px;line-height:1.4}
        .gaia-dashboard__stat-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
        @media(min-width:900px){.gaia-dashboard__stat-grid{grid-template-columns:repeat(4,minmax(0,1fr));}}
        .gaia-dashboard__stat-box{padding:12px;border-radius:12px;background:#172130;border:1px solid rgba(255,255,255,.08)}
        .gaia-dashboard__stat-box strong{display:block;font-size:12px;color:#8f9db7;text-transform:uppercase;letter-spacing:.05em}
        .gaia-dashboard__stat-box span{display:block;margin-top:6px;font-size:20px;font-weight:700;color:#fff}
        .gaia-dashboard__list{display:flex;flex-direction:column;gap:10px}
        .gaia-dashboard__list-row{padding:12px;border-radius:12px;background:#172130;border:1px solid rgba(255,255,255,.06)}
        .gaia-dashboard__list-row strong{display:block;font-size:14px}
        .gaia-dashboard__list-row p{margin:6px 0 0;font-size:13px;line-height:1.45;color:#9da9c1}
        .gaia-dashboard__split{display:grid;grid-template-columns:1fr;gap:14px}
        @media(min-width:1000px){.gaia-dashboard__split{grid-template-columns:1.3fr .9fr;}}
        .gaia-dashboard__form{display:flex;flex-direction:column;gap:12px}
        .gaia-dashboard__form-grid{display:grid;grid-template-columns:1fr;gap:10px}
        @media(min-width:900px){.gaia-dashboard__form-grid{grid-template-columns:repeat(2,minmax(0,1fr));}}
        .gaia-dashboard__field{display:flex;flex-direction:column;gap:6px}
        .gaia-dashboard__field label{font-size:12px;color:#9da9c1}
        .gaia-dashboard__field input,.gaia-dashboard__field select,.gaia-dashboard__field textarea{width:100%;border-radius:12px;border:1px solid rgba(255,255,255,.1);background:#101826;color:#e8edf7;padding:10px 12px}
        .gaia-dashboard__field textarea{min-height:84px;resize:vertical}
        .gaia-dashboard__exposure-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;align-items:start}
        .gaia-dashboard__toggle-chip{display:flex;align-items:flex-start;gap:10px;padding:12px 14px;border-radius:14px;background:#172130;border:1px solid rgba(255,255,255,.08);color:#d6e3fa;font-size:14px;line-height:1.45;min-height:0}
        .gaia-dashboard__toggle-chip input{accent-color:#2b8cff;flex:0 0 auto;margin-top:3px}
        .gaia-dashboard__toggle-chip span{display:block;flex:1 1 auto;min-width:0;white-space:normal;overflow-wrap:break-word;word-break:normal}
        .gaia-dashboard__helper{font-size:12px;color:#9da9c1;line-height:1.45}
        .gaia-dashboard__status-note{font-size:12px;color:#d8b176}
        .gaia-dashboard__link-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;align-items:start}
        .gaia-dashboard__link-grid--settings{grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}
        .gaia-dashboard__link-card{display:flex;flex-direction:column;gap:6px;padding:14px;border-radius:14px;background:#151c28;border:1px solid rgba(255,255,255,.08);text-decoration:none;color:#e8edf7;min-height:0}
        .gaia-dashboard__link-card small{color:#9da9c1;line-height:1.45}
        .gaia-dashboard__empty{padding:16px;border-radius:14px;background:#121925;border:1px dashed rgba(255,255,255,.08);font-size:13px;color:#9da9c1;line-height:1.5}
        .gaia-dashboard__pill-row{display:flex;flex-wrap:wrap;gap:8px}
        .gaia-dashboard__pill-button{border:1px solid rgba(255,255,255,.08);border-radius:999px;background:#172130;color:#d7e6ff;padding:8px 12px;font-weight:600;cursor:pointer}
        .gaia-dashboard__pill-button.is-active{background:#224064;border-color:rgba(156,192,255,.38)}
        .gaia-dashboard__section-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
        .gaia-dashboard__mini-title{font-size:13px;font-weight:700;color:#eef4ff}
        .gaia-dashboard__driver-pill{display:inline-flex;align-items:center;gap:6px;padding:6px 10px;border-radius:999px;background:#1a2434;color:#cdd9ef;font-size:12px}
        .gaia-dashboard__guide-stack{display:grid;grid-template-columns:1fr;gap:12px}
        @media(min-width:960px){.gaia-dashboard__guide-stack{grid-template-columns:repeat(2,minmax(0,1fr));}}
        .gaia-dashboard__guide-bullet-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;align-items:start}
        @media(max-width:520px){.gaia-dashboard__guide-bullet-grid{grid-template-columns:1fr;}}
        .gaia-dashboard__guide-bullet-grid--compact{gap:8px}
        .gaia-dashboard__card-title-row--guide{align-items:center}
        .gaia-dashboard__guide-settings-btn{display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;border-radius:999px;border:1px solid rgba(84,201,255,.24);background:rgba(62,177,255,.14);color:#e6f2ff;cursor:pointer}
        .gaia-dashboard__guide-topline{margin:0;font-size:12px;font-weight:700;line-height:1.45;color:#a8c6df}
        .gaia-dashboard__guide-profile-line{font-size:12px;color:#8f9db7;line-height:1.4}
        .gaia-dashboard__guide-bullet{padding:10px 12px;border-radius:12px;background:rgba(62,177,255,.12);border:1px solid rgba(62,177,255,.12);font-size:13px;font-weight:600;line-height:1.45;color:#e6f2ff;min-width:0}
        .gaia-dashboard__guide-influence-stack{display:flex;flex-direction:column;gap:12px}
        .gaia-dashboard__guide-influence-section{padding:12px;border-radius:14px;background:#151d2a;border:1px solid rgba(255,255,255,.08);display:flex;flex-direction:column;gap:8px;min-width:0}
        .gaia-dashboard__guide-bullet-list{display:flex;flex-direction:column;gap:8px;min-width:0}
        .gaia-dashboard__guide-bullet-row{padding:10px 12px;border-radius:12px;background:rgba(62,177,255,.10);font-size:14px;font-weight:600;line-height:1.5;color:#e6f2ff;white-space:normal;overflow-wrap:anywhere}
        .gaia-dashboard__poll-choices{display:flex;flex-wrap:wrap;gap:8px}
        .gaia-dashboard__poll-choice{border:1px solid rgba(255,255,255,.08);border-radius:999px;background:#172130;color:#e8edf7;padding:8px 14px;cursor:pointer;font-weight:600}
        .gaia-dashboard__poll-choice.is-selected{background:#224064;border-color:rgba(156,192,255,.38)}
        .gaia-dashboard__outlook-signal-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;align-items:start}
        .gaia-dashboard__outlook-signal-card{padding:10px 12px;border-radius:12px;background:#172130;border:1px solid rgba(255,255,255,.08);min-width:0}
        .gaia-dashboard__outlook-signal-label{font-size:11px;color:#8f9db7;text-transform:uppercase;letter-spacing:.06em;line-height:1.35}
        .gaia-dashboard__outlook-signal-value{margin-top:6px;font-size:18px;font-weight:700;color:#eef4ff;line-height:1.2}
        .gaia-dashboard__outlook-domain-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;align-items:start}
        .gaia-dashboard__outlook-domain{padding:12px;border-radius:12px;background:#172130;border:1px solid rgba(255,255,255,.08)}
        .gaia-dashboard__outlook-domain-head{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}
        .gaia-dashboard__outlook-domain-head strong{font-size:14px;line-height:1.25}
        .gaia-dashboard__outlook-domain p{margin:8px 0 0;font-size:14px;line-height:1.55;color:#c9d4e8}
        .gaia-dashboard__modal{position:fixed;inset:0;z-index:99999;display:none}
        .gaia-dashboard__modal.is-open{display:block}
        .gaia-dashboard__modal-backdrop{position:absolute;inset:0;background:rgba(2,6,12,.72)}
        .gaia-dashboard__modal-card{position:relative;width:min(94vw,920px);max-width:920px;margin:7vh auto;background:#101826;border:1px solid rgba(255,255,255,.12);border-radius:14px;padding:18px;max-height:84vh;overflow:auto;color:#e8edf7}
        .gaia-dashboard__modal-title{margin:0 0 10px;font-size:22px}
        .gaia-dashboard__modal-group{margin-top:12px}
        .gaia-dashboard__modal-group h5{margin:0 0 7px;font-size:15px}
        .gaia-dashboard__modal-group ul{margin:0;padding-left:18px}
        .gaia-dashboard__modal-group li{margin:0 0 6px;line-height:1.45}
        @media(max-width:900px){
          .gaia-dashboard__shell--hub{padding-bottom:110px}
          .gaia-dashboard__sticky-tabs{display:none}
          .gaia-dashboard__nav-grid--hub{display:none}
          .gaia-dashboard__mobile-tabbar{position:fixed;left:12px;right:12px;bottom:calc(10px + env(safe-area-inset-bottom,0px));display:block;max-width:760px;margin:0 auto;padding:8px;border-radius:22px;background:rgba(10,14,22,.94);border:1px solid rgba(255,255,255,.1);box-shadow:0 18px 40px rgba(0,0,0,.38);backdrop-filter:blur(16px);z-index:99990}
        }
        .gaia-dashboard__modal-copy{margin:0;color:#e8edf7;line-height:1.55}
        .gaia-dashboard__quicklog-pills{display:flex;flex-wrap:wrap;gap:10px;margin-top:10px}
        .gaia-dashboard__quicklog-pill{border:1px solid rgba(255,255,255,.12);border-radius:999px;padding:8px 14px;background:#182234;color:#e8edf7;font-weight:600;cursor:pointer}
        .gaia-dashboard__quicklog-pill.is-selected{border-color:#67a7ff;background:#213150}
        .gaia-dashboard__symptom-sheet{display:flex;flex-direction:column;gap:16px}
        .gaia-dashboard__symptom-hero{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap}
        .gaia-dashboard__symptom-hero-copy{display:flex;flex-direction:column;gap:6px;max-width:420px}
        .gaia-dashboard__symptom-count{display:inline-flex;align-items:center;justify-content:center;min-width:38px;height:38px;padding:0 12px;border-radius:999px;background:#213150;border:1px solid rgba(103,167,255,.28);color:#dce9ff;font-weight:700}
        .gaia-dashboard__symptom-section{padding:14px;border-radius:14px;background:#151d2a;border:1px solid rgba(255,255,255,.08);display:flex;flex-direction:column;gap:10px}
        .gaia-dashboard__symptom-section-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;flex-wrap:wrap}
        .gaia-dashboard__symptom-section-copy{display:flex;flex-direction:column;gap:4px}
        .gaia-dashboard__symptom-section-title{margin:0;font-size:15px;line-height:1.25}
        .gaia-dashboard__symptom-grid{display:grid;grid-template-columns:1fr;gap:10px}
        @media(min-width:640px){.gaia-dashboard__symptom-grid{grid-template-columns:repeat(2,minmax(0,1fr));}}
        .gaia-dashboard__symptom-search{width:100%;border-radius:12px;border:1px solid rgba(255,255,255,.10);background:#101826;color:#e8edf7;padding:11px 12px;font-size:14px}
        .gaia-dashboard__symptom-pill{display:flex;flex-direction:column;align-items:flex-start;gap:4px;border:1px solid rgba(255,255,255,.10);border-radius:14px;padding:12px 14px;background:#172130;color:#e8edf7;cursor:pointer;text-align:left;transition:border-color .15s ease,background .15s ease,transform .15s ease}
        .gaia-dashboard__symptom-pill:hover{transform:translateY(-1px);border-color:rgba(156,192,255,.28)}
        .gaia-dashboard__symptom-pill[disabled]{opacity:.48;cursor:not-allowed;transform:none}
        .gaia-dashboard__symptom-pill.is-selected{border-color:#67a7ff;background:#213150;box-shadow:0 0 0 1px rgba(103,167,255,.16) inset}
        .gaia-dashboard__symptom-pill-title{font-size:14px;font-weight:700;line-height:1.25}
        .gaia-dashboard__symptom-pill-copy{font-size:12px;line-height:1.45;color:#a9b8d4}
        .gaia-dashboard__symptom-selected{display:flex;flex-wrap:wrap;gap:8px}
        .gaia-dashboard__symptom-selected-chip{display:inline-flex;align-items:center;gap:8px;padding:7px 11px;border-radius:999px;background:#213150;border:1px solid rgba(103,167,255,.26);color:#e8f2ff;font-size:12px;font-weight:650}
        .gaia-dashboard__symptom-selected-chip button{border:0;background:transparent;color:inherit;cursor:pointer;padding:0;font-size:14px;line-height:1}
        .gaia-dashboard__symptom-empty{padding:12px;border-radius:12px;background:#121925;border:1px dashed rgba(255,255,255,.08);font-size:13px;color:#9da9c1;line-height:1.5}
        .gaia-dashboard__current-symptom-list{display:flex;flex-direction:column;gap:10px;margin-top:12px}
        .gaia-dashboard__current-symptom-row{padding:12px;border-radius:14px;background:#151d2a;border:1px solid rgba(255,255,255,.08);display:flex;flex-direction:column;gap:10px}
        .gaia-dashboard__current-symptom-row.is-pending{border-color:rgba(103,167,255,.28);box-shadow:0 0 0 1px rgba(103,167,255,.14) inset}
        .gaia-dashboard__current-symptom-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}
        .gaia-dashboard__current-symptom-copy{display:flex;flex-direction:column;gap:4px;min-width:0}
        .gaia-dashboard__current-symptom-copy strong{font-size:15px;line-height:1.25}
        .gaia-dashboard__current-symptom-copy span{font-size:12px;color:#9da9c1;line-height:1.45}
        .gaia-dashboard__current-symptom-actions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
        .gaia-dashboard__current-symptom-subactions{display:flex;flex-wrap:wrap;gap:8px}
        .gaia-dashboard__current-symptom-btn{border:1px solid rgba(255,255,255,.08);border-radius:999px;background:#172130;color:#e8edf7;padding:8px 12px;font-weight:650;cursor:pointer;transition:border-color .15s ease,background .15s ease}
        .gaia-dashboard__current-symptom-btn:hover{border-color:rgba(156,192,255,.28)}
        .gaia-dashboard__current-symptom-btn.is-selected{background:#213150;border-color:#67a7ff}
        .gaia-dashboard__current-symptom-btn.is-positive{background:rgba(79,154,123,.16);border-color:rgba(120,210,169,.34)}
        .gaia-dashboard__current-symptom-btn.is-warning{background:rgba(208,134,85,.16);border-color:rgba(224,171,118,.34)}
        .gaia-dashboard__current-symptom-btn.is-danger{background:rgba(187,92,97,.14);border-color:rgba(230,122,126,.32)}
        .gaia-dashboard__current-symptom-btn[disabled]{opacity:.55;cursor:not-allowed}
        .gaia-dashboard__current-symptom-feedback{font-size:12px;line-height:1.45;color:#a9b8d4}
        .gaia-dashboard__current-symptom-feedback.is-error{color:#ffb26c}
        .gaia-dashboard__support-list{display:flex;flex-direction:column;gap:10px}
        .gaia-dashboard__support-card{padding:12px;border-radius:14px;background:#151d2a;border:1px solid rgba(255,255,255,.08);display:flex;flex-direction:column;gap:8px}
        .gaia-dashboard__support-card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}
        .gaia-dashboard__support-card-title{font-size:15px;font-weight:700;line-height:1.3}
        .gaia-dashboard__support-card-copy{font-size:14px;line-height:1.55;color:#d5deef}
        .gaia-dashboard__support-actions{display:flex;flex-wrap:wrap;gap:8px}
        .gaia-dashboard__modal-status-row{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:12px;flex-wrap:wrap}
        .gaia-dashboard__modal-actions{display:flex;justify-content:space-between;gap:10px;margin-top:16px;flex-wrap:wrap}
        body.gaia-modal-open{overflow:hidden}
    ');
});

add_action('wp_head', function () {
    ?>
    <script id="gaia-auth-hash-guard">
    (function () {
      try {
        var h = window.location.hash || "";
        if (!h || h.length < 2) return;
        var frag = h.slice(1);
        if (frag.indexOf("access_token=") === -1 && frag.indexOf("refresh_token=") === -1) return;
        try { sessionStorage.setItem("gaia_auth_fragment", frag); } catch (e) {}
        if (window.history && window.history.replaceState) {
          window.history.replaceState({}, document.title, window.location.pathname + window.location.search);
        }
      } catch (e) {}
    })();
    </script>
    <?php
}, 1);

if (!function_exists('gaia_dashboard_shortcode_render')) {
function gaia_dashboard_shortcode_render($atts = []) {
    $a = shortcode_atts([
        'title' => 'Mission Control',
    ], $atts, 'gaia_dashboard');

    wp_enqueue_script('supabase-js', 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2', [], null, true);
    wp_enqueue_script('gaia-dashboard');
    wp_enqueue_style('gaia-dashboard');

    ob_start();
    ?>
    <section class="gaia-dashboard" data-gaia-dashboard data-title="<?php echo esc_attr($a['title']); ?>">
        <div class="gaia-dashboard__status">Loading dashboard...</div>
    </section>
    <?php
    return ob_get_clean();
}
}

add_action('init', function () {
    if (!shortcode_exists('gaia_dashboard')) {
        add_shortcode('gaia_dashboard', 'gaia_dashboard_shortcode_render');
    }
    if (!shortcode_exists('gaia_member_hub')) {
        add_shortcode('gaia_member_hub', 'gaia_dashboard_shortcode_render');
    }
});

add_filter('the_content', function ($content) {
    if (strpos($content, '[gaia_dashboard') === false && strpos($content, '[gaia_member_hub') === false) {
        return $content;
    }
    return do_shortcode($content);
}, 20);

if (!function_exists('gaia_dashboard_backend_base')) {
function gaia_dashboard_backend_base() {
    $backend_base = defined('GAIAEYES_API_BASE') ? GAIAEYES_API_BASE : getenv('GAIAEYES_API_BASE');
    return $backend_base ? rtrim((string) $backend_base, '/') : '';
}
}

if (!function_exists('gaia_dashboard_backend_bearer')) {
function gaia_dashboard_backend_bearer() {
    $bearer = defined('GAIAEYES_API_BEARER') ? GAIAEYES_API_BEARER : getenv('GAIAEYES_API_BEARER');
    return is_string($bearer) ? trim($bearer) : '';
}
}

if (!function_exists('gaia_dashboard_forwarded_auth_header')) {
function gaia_dashboard_forwarded_auth_header(WP_REST_Request $request) {
    $auth = (string) $request->get_header('authorization');
    if (!$auth && isset($_SERVER['HTTP_AUTHORIZATION'])) {
        $auth = (string) wp_unslash($_SERVER['HTTP_AUTHORIZATION']);
    }
    return $auth;
}
}

if (!function_exists('gaia_bug_reports_fetch_recent')) {
function gaia_bug_reports_fetch_recent($limit = 50) {
    $backend_base = gaia_dashboard_backend_base();
    $bearer = gaia_dashboard_backend_bearer();

    if ($backend_base === '') {
        return new WP_Error('gaia_bug_reports_backend_missing', 'GAIAEYES_API_BASE is not configured.');
    }
    if ($bearer === '') {
        return new WP_Error('gaia_bug_reports_bearer_missing', 'GAIAEYES_API_BEARER is not configured.');
    }

    $url = add_query_arg(
        ['limit' => max(1, min((int) $limit, 200))],
        $backend_base . '/v1/profile/bug-reports'
    );

    $resp = wp_remote_get($url, [
        'timeout' => 20,
        'headers' => [
            'Accept' => 'application/json',
            'Authorization' => 'Bearer ' . $bearer,
        ],
    ]);
    if (is_wp_error($resp)) {
        return $resp;
    }

    $status = (int) wp_remote_retrieve_response_code($resp);
    $body = (string) wp_remote_retrieve_body($resp);
    $decoded = json_decode($body, true);
    if (!is_array($decoded)) {
        return new WP_Error('gaia_bug_reports_invalid_json', 'Bug reports endpoint returned invalid JSON.');
    }
    if ($status < 200 || $status >= 300 || empty($decoded['ok'])) {
        return new WP_Error(
            'gaia_bug_reports_fetch_failed',
            isset($decoded['error']) && is_string($decoded['error']) ? $decoded['error'] : 'Bug reports fetch failed.'
        );
    }
    $data = isset($decoded['data']) && is_array($decoded['data']) ? $decoded['data'] : [];
    $reports = isset($data['reports']) && is_array($data['reports']) ? $data['reports'] : [];
    return $reports;
}
}

if (!function_exists('gaia_bug_reports_render_admin_page')) {
function gaia_bug_reports_render_admin_page() {
    if (!current_user_can('manage_options')) {
        wp_die('You do not have permission to view this page.');
    }

    $reports = gaia_bug_reports_fetch_recent(60);
    ?>
    <div class="wrap">
        <h1>Gaia Bug Reports</h1>
        <p>Recent in-app bug submissions with attached diagnostics bundles.</p>
        <style>
            .gaia-bug-reports{display:flex;flex-direction:column;gap:16px;max-width:1100px}
            .gaia-bug-report{background:#fff;border:1px solid #dcdcde;border-radius:12px;padding:16px}
            .gaia-bug-report__head{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;flex-wrap:wrap}
            .gaia-bug-report__meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin-top:12px}
            .gaia-bug-report__meta div{background:#f6f7f7;border-radius:10px;padding:10px}
            .gaia-bug-report__meta strong{display:block;font-size:11px;color:#50575e;text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px}
            .gaia-bug-report__desc{font-size:14px;line-height:1.55;margin:12px 0 0}
            .gaia-bug-report__status{display:inline-flex;align-items:center;gap:6px;padding:6px 10px;border-radius:999px;background:#eef4ff;color:#1d4d8f;font-weight:600}
            .gaia-bug-report__status.is-failed{background:#fff1f0;color:#8a2424}
            .gaia-bug-report details{margin-top:14px}
            .gaia-bug-report summary{cursor:pointer;font-weight:600}
            .gaia-bug-report textarea{width:100%;min-height:280px;margin-top:10px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
            .gaia-bug-reports__empty{padding:16px;background:#fff;border:1px solid #dcdcde;border-radius:12px}
            .gaia-bug-reports__error{padding:16px;background:#fff1f0;border:1px solid #f0c0bb;border-radius:12px;color:#8a2424}
        </style>
        <?php if (is_wp_error($reports)): ?>
            <div class="gaia-bug-reports__error">
                <strong>Could not load bug reports.</strong>
                <p><?php echo esc_html($reports->get_error_message()); ?></p>
            </div>
        <?php elseif (empty($reports)): ?>
            <div class="gaia-bug-reports__empty">No bug reports yet.</div>
        <?php else: ?>
            <div class="gaia-bug-reports">
                <?php foreach ($reports as $report): ?>
                    <?php
                    $report_id = isset($report['id']) ? (string) $report['id'] : '';
                    $description = isset($report['description']) ? (string) $report['description'] : '';
                    $diagnostics = isset($report['diagnostics_bundle']) ? (string) $report['diagnostics_bundle'] : '';
                    $alert_sent = !empty($report['alert_sent']);
                    $alert_response = isset($report['alert_response']) ? $report['alert_response'] : null;
                    $alert_response_text = is_array($alert_response)
                        ? wp_json_encode($alert_response, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES)
                        : (is_string($alert_response) ? $alert_response : '');
                    ?>
                    <section class="gaia-bug-report">
                        <div class="gaia-bug-report__head">
                            <div>
                                <h2 style="margin:0 0 6px;"><?php echo esc_html($report_id !== '' ? $report_id : 'Bug report'); ?></h2>
                                <p class="gaia-bug-report__desc"><?php echo esc_html($description !== '' ? $description : 'No description provided.'); ?></p>
                            </div>
                            <span class="gaia-bug-report__status<?php echo $alert_sent ? '' : ' is-failed'; ?>">
                                <?php echo esc_html($alert_sent ? 'Alert sent' : 'Alert pending'); ?>
                            </span>
                        </div>
                        <div class="gaia-bug-report__meta">
                            <div><strong>Created</strong><span><?php echo esc_html(isset($report['created_at']) ? (string) $report['created_at'] : '—'); ?></span></div>
                            <div><strong>User</strong><span><?php echo esc_html(isset($report['user_id']) ? (string) $report['user_id'] : '—'); ?></span></div>
                            <div><strong>Source</strong><span><?php echo esc_html(isset($report['source']) ? (string) $report['source'] : '—'); ?></span></div>
                            <div><strong>App</strong><span><?php echo esc_html(isset($report['app_version']) ? (string) $report['app_version'] : '—'); ?></span></div>
                            <div><strong>Device</strong><span><?php echo esc_html(isset($report['device']) ? (string) $report['device'] : '—'); ?></span></div>
                            <div><strong>Alert email to</strong><span><?php echo esc_html(isset($report['alert_email_to']) && $report['alert_email_to'] !== '' ? (string) $report['alert_email_to'] : '—'); ?></span></div>
                            <div><strong>Alert error</strong><span><?php echo esc_html(isset($report['alert_error']) && $report['alert_error'] !== '' ? (string) $report['alert_error'] : '—'); ?></span></div>
                        </div>
                        <?php if ($alert_response_text !== ''): ?>
                            <details>
                                <summary>Alert response</summary>
                                <textarea readonly><?php echo esc_textarea($alert_response_text); ?></textarea>
                            </details>
                        <?php endif; ?>
                        <details>
                            <summary>Diagnostics bundle</summary>
                            <textarea readonly><?php echo esc_textarea($diagnostics); ?></textarea>
                        </details>
                    </section>
                <?php endforeach; ?>
            </div>
        <?php endif; ?>
    </div>
    <?php
}
}

add_action('admin_menu', function () {
    add_management_page(
        'Gaia Bug Reports',
        'Gaia Bug Reports',
        'manage_options',
        'gaia-bug-reports',
        'gaia_bug_reports_render_admin_page'
    );
});

if (!function_exists('gaia_dashboard_proxy_json')) {
function gaia_dashboard_proxy_json(
    WP_REST_Request $request,
    string $backend_path,
    array $query_map = [],
    string $method = WP_REST_Server::READABLE
) {
    $backend_base = gaia_dashboard_backend_base();
    if ($backend_base === '') {
        return new WP_REST_Response(['ok' => false, 'error' => 'GAIAEYES_API_BASE is not configured'], 500);
    }

    $query_args = [];
    foreach ($query_map as $request_key => $backend_key) {
        $value = $request->get_param($request_key);
        if ($value === null || $value === '') {
            continue;
        }
        $query_args[$backend_key] = sanitize_text_field((string) $value);
    }

    $url = add_query_arg($query_args, $backend_base . $backend_path);

    $headers = ['Accept' => 'application/json'];
    $auth = gaia_dashboard_forwarded_auth_header($request);
    if ($auth !== '') {
        $headers['Authorization'] = $auth;
    }

    $args = [
        'timeout' => 20,
        'method' => $method,
        'headers' => $headers,
    ];

    if ($method !== WP_REST_Server::READABLE && $method !== 'GET') {
        $headers['Content-Type'] = 'application/json';
        $args['headers'] = $headers;
        $args['body'] = (string) $request->get_body();
    }

    $resp = wp_remote_request($url, $args);

    if (is_wp_error($resp)) {
        return new WP_REST_Response([
            'ok' => false,
            'error' => 'member hub proxy fetch failed',
            'detail' => $resp->get_error_message(),
        ], 502);
    }

    $status = (int) wp_remote_retrieve_response_code($resp);
    $body = (string) wp_remote_retrieve_body($resp);
    $decoded = json_decode($body, true);

    if (!is_array($decoded)) {
        return new WP_REST_Response([
            'ok' => false,
            'error' => 'member hub proxy invalid JSON',
            'status' => $status,
        ], 502);
    }

    return new WP_REST_Response($decoded, $status > 0 ? $status : 200);
}
}

if (!function_exists('gaia_dashboard_proxy_backend')) {
function gaia_dashboard_proxy_backend(WP_REST_Request $request) {
    $day = sanitize_text_field((string) ($request->get_param('day') ?: ''));
    if (!$day) {
        $day = gmdate('Y-m-d');
    }
    if (!$request->get_param('day')) {
        $request->set_param('day', $day);
    }
    $debug = $request->get_param('debug');
    if ($debug !== null && $debug !== '' && $debug !== '0' && $debug !== 0 && $debug !== false) {
        $request->set_param('debug', '1');
    }

    return gaia_dashboard_proxy_json(
        $request,
        '/v1/dashboard',
        [
            'day' => 'day',
            'debug' => 'debug',
        ]
    );
}
}

if (!function_exists('gaia_bug_report_alert_secret')) {
function gaia_bug_report_alert_secret() {
    $defined = defined('GAIA_BUG_REPORT_ALERT_SECRET') ? GAIA_BUG_REPORT_ALERT_SECRET : '';
    if (is_string($defined) && trim($defined) !== '') {
        return trim($defined);
    }
    $env = getenv('GAIA_BUG_REPORT_ALERT_SECRET');
    return is_string($env) ? trim($env) : '';
}
}

if (!function_exists('gaia_bug_report_alert_email')) {
function gaia_bug_report_alert_email() {
    $email = defined('GAIA_BUG_REPORT_ALERT_EMAIL') ? GAIA_BUG_REPORT_ALERT_EMAIL : getenv('GAIA_BUG_REPORT_ALERT_EMAIL');
    $email = is_string($email) ? trim($email) : '';
    if ($email === '') {
        $email = 'help@gaiaeyes.com';
    }
    return apply_filters('gaia_bug_report_alert_email', $email);
}
}

if (!function_exists('gaia_bug_report_alert_permission')) {
function gaia_bug_report_alert_permission(WP_REST_Request $request) {
    $configured = gaia_bug_report_alert_secret();
    if ($configured === '') {
        return new WP_Error('gaia_bug_report_secret_missing', 'Bug report alert secret is not configured.', ['status' => 503]);
    }

    $provided = $request->get_header('X-Gaia-Bug-Secret');
    if (!is_string($provided) || trim($provided) === '') {
        return new WP_Error('gaia_bug_report_forbidden', 'Missing bug report alert secret.', ['status' => 403]);
    }

    if (!hash_equals($configured, trim($provided))) {
        return new WP_Error('gaia_bug_report_forbidden', 'Invalid bug report alert secret.', ['status' => 403]);
    }

    return true;
}
}

if (!function_exists('gaia_bug_report_alert_callback')) {
function gaia_bug_report_alert_callback(WP_REST_Request $request) {
    $payload = $request->get_json_params();
    if (!is_array($payload)) {
        $payload = [];
    }

    $report_id = isset($payload['report_id']) ? sanitize_text_field((string) $payload['report_id']) : '';
    $user_id = isset($payload['user_id']) ? sanitize_text_field((string) $payload['user_id']) : '';
    $source = isset($payload['source']) ? sanitize_text_field((string) $payload['source']) : 'unknown';
    $description = isset($payload['description']) ? trim(wp_strip_all_tags((string) $payload['description'])) : '';
    $app_version = isset($payload['app_version']) ? sanitize_text_field((string) $payload['app_version']) : '';
    $device = isset($payload['device']) ? sanitize_text_field((string) $payload['device']) : '';
    $created_at = isset($payload['created_at']) ? sanitize_text_field((string) $payload['created_at']) : '';

    if ($report_id === '' || $description === '') {
        return new WP_REST_Response([
            'ok' => false,
            'error' => 'missing bug report fields',
        ], 400);
    }

    $to = gaia_bug_report_alert_email();
    $subject = sprintf('[Gaia Eyes] New bug report %s', $report_id);
    $lines = [
        'A new Gaia Eyes bug report was submitted.',
        '',
        'Report ID: ' . $report_id,
        'User ID: ' . ($user_id !== '' ? $user_id : '—'),
        'Source: ' . $source,
        'App version: ' . ($app_version !== '' ? $app_version : '—'),
        'Device: ' . ($device !== '' ? $device : '—'),
        'Created at: ' . ($created_at !== '' ? $created_at : '—'),
        '',
        'Description:',
        $description,
    ];
    $sent = wp_mail($to, $subject, implode("\n", $lines));

    return new WP_REST_Response([
        'ok' => (bool) $sent,
        'email_sent' => (bool) $sent,
        'email_to' => $to,
        'report_id' => $report_id,
    ], $sent ? 200 : 500);
}
}

add_action('rest_api_init', function () {
    register_rest_route('gaia/v1', '/dashboard', [
        'methods' => WP_REST_Server::READABLE,
        'permission_callback' => '__return_true',
        'callback' => 'gaia_dashboard_proxy_backend',
        'args' => [
            'day' => [
                'required' => false,
                'sanitize_callback' => 'sanitize_text_field',
            ],
            'debug' => [
                'required' => false,
                'sanitize_callback' => 'sanitize_text_field',
            ],
        ],
    ]);

    register_rest_route('gaia/v1', '/member/drivers', [
        'methods' => WP_REST_Server::READABLE,
        'permission_callback' => '__return_true',
        'callback' => function (WP_REST_Request $request) {
            return gaia_dashboard_proxy_json($request, '/v1/users/me/drivers', ['day' => 'day']);
        },
        'args' => [
            'day' => [
                'required' => false,
                'sanitize_callback' => 'sanitize_text_field',
            ],
        ],
    ]);

    register_rest_route('gaia/v1', '/member/outlook', [
        'methods' => WP_REST_Server::READABLE,
        'permission_callback' => '__return_true',
        'callback' => function (WP_REST_Request $request) {
            return gaia_dashboard_proxy_json($request, '/v1/users/me/outlook');
        },
    ]);

    register_rest_route('gaia/v1', '/member/patterns-summary', [
        'methods' => WP_REST_Server::READABLE,
        'permission_callback' => '__return_true',
        'callback' => function (WP_REST_Request $request) {
            return gaia_dashboard_proxy_json($request, '/v1/patterns/summary');
        },
    ]);

    register_rest_route('gaia/v1', '/member/patterns', [
        'methods' => WP_REST_Server::READABLE,
        'permission_callback' => '__return_true',
        'callback' => function (WP_REST_Request $request) {
            return gaia_dashboard_proxy_json($request, '/v1/patterns');
        },
    ]);

    register_rest_route('gaia/v1', '/member/features', [
        'methods' => WP_REST_Server::READABLE,
        'permission_callback' => '__return_true',
        'callback' => function (WP_REST_Request $request) {
            return gaia_dashboard_proxy_json($request, '/v1/features/today', ['tz' => 'tz']);
        },
        'args' => [
            'tz' => [
                'required' => false,
                'sanitize_callback' => 'sanitize_text_field',
            ],
        ],
    ]);

    register_rest_route('gaia/v1', '/member/symptom-codes', [
        'methods' => WP_REST_Server::READABLE,
        'permission_callback' => '__return_true',
        'callback' => function (WP_REST_Request $request) {
            return gaia_dashboard_proxy_json($request, '/v1/symptoms/codes');
        },
    ]);

    register_rest_route('gaia/v1', '/member/symptoms', [
        'methods' => WP_REST_Server::CREATABLE,
        'permission_callback' => '__return_true',
        'callback' => function (WP_REST_Request $request) {
            return gaia_dashboard_proxy_json($request, '/v1/symptoms', [], WP_REST_Server::CREATABLE);
        },
    ]);

    register_rest_route('gaia/v1', '/member/current-symptoms', [
        'methods' => WP_REST_Server::READABLE,
        'permission_callback' => '__return_true',
        'callback' => function (WP_REST_Request $request) {
            return gaia_dashboard_proxy_json($request, '/v1/symptoms/current', ['window_hours' => 'window_hours']);
        },
        'args' => [
            'window_hours' => [
                'required' => false,
                'sanitize_callback' => 'absint',
            ],
        ],
    ]);

    register_rest_route('gaia/v1', '/member/current-symptoms/(?P<episode_id>[^/]+)/updates', [
        'methods' => WP_REST_Server::CREATABLE,
        'permission_callback' => '__return_true',
        'callback' => function (WP_REST_Request $request) {
            $episode_id = sanitize_text_field((string) $request['episode_id']);
            return gaia_dashboard_proxy_json(
                $request,
                '/v1/symptoms/current/' . rawurlencode($episode_id) . '/updates',
                [],
                WP_REST_Server::CREATABLE
            );
        },
    ]);

    register_rest_route('gaia/v1', '/member/follow-ups/(?P<prompt_id>[^/]+)/respond', [
        'methods' => WP_REST_Server::CREATABLE,
        'permission_callback' => '__return_true',
        'callback' => function (WP_REST_Request $request) {
            $prompt_id = sanitize_text_field((string) $request['prompt_id']);
            return gaia_dashboard_proxy_json(
                $request,
                '/v1/symptoms/follow-ups/' . rawurlencode($prompt_id) . '/respond',
                [],
                WP_REST_Server::CREATABLE
            );
        },
    ]);

    register_rest_route('gaia/v1', '/member/follow-ups/(?P<prompt_id>[^/]+)/dismiss', [
        'methods' => WP_REST_Server::CREATABLE,
        'permission_callback' => '__return_true',
        'callback' => function (WP_REST_Request $request) {
            $prompt_id = sanitize_text_field((string) $request['prompt_id']);
            return gaia_dashboard_proxy_json(
                $request,
                '/v1/symptoms/follow-ups/' . rawurlencode($prompt_id) . '/dismiss',
                [],
                WP_REST_Server::CREATABLE
            );
        },
    ]);

    register_rest_route('gaia/v1', '/member/daily-checkin', [
        [
            'methods' => WP_REST_Server::READABLE,
            'permission_callback' => '__return_true',
            'callback' => function (WP_REST_Request $request) {
                return gaia_dashboard_proxy_json($request, '/v1/feedback/daily-checkin');
            },
        ],
        [
            'methods' => WP_REST_Server::CREATABLE,
            'permission_callback' => '__return_true',
            'callback' => function (WP_REST_Request $request) {
                return gaia_dashboard_proxy_json($request, '/v1/feedback/daily-checkin', [], WP_REST_Server::CREATABLE);
            },
        ],
    ]);

    register_rest_route('gaia/v1', '/member/daily-checkin/(?P<prompt_id>[^/]+)/dismiss', [
        'methods' => WP_REST_Server::CREATABLE,
        'permission_callback' => '__return_true',
        'callback' => function (WP_REST_Request $request) {
            $prompt_id = sanitize_text_field((string) $request['prompt_id']);
            return gaia_dashboard_proxy_json(
                $request,
                '/v1/feedback/daily-checkin/' . rawurlencode($prompt_id) . '/dismiss',
                [],
                WP_REST_Server::CREATABLE
            );
        },
    ]);

    register_rest_route('gaia/v1', '/member/lunar', [
        'methods' => WP_REST_Server::READABLE,
        'permission_callback' => '__return_true',
        'callback' => function (WP_REST_Request $request) {
            return gaia_dashboard_proxy_json($request, '/v1/insights/lunar');
        },
    ]);

    register_rest_route('gaia/v1', '/member/local-check', [
        'methods' => WP_REST_Server::READABLE,
        'permission_callback' => '__return_true',
        'callback' => function (WP_REST_Request $request) {
            return gaia_dashboard_proxy_json($request, '/v1/local/check', ['zip' => 'zip']);
        },
        'args' => [
            'zip' => [
                'required' => false,
                'sanitize_callback' => 'sanitize_text_field',
            ],
        ],
    ]);

    register_rest_route('gaia/v1', '/member/profile-preferences', [
        [
            'methods' => WP_REST_Server::READABLE,
            'permission_callback' => '__return_true',
            'callback' => function (WP_REST_Request $request) {
                return gaia_dashboard_proxy_json($request, '/v1/profile/preferences');
            },
        ],
        [
            'methods' => WP_REST_Server::EDITABLE,
            'permission_callback' => '__return_true',
            'callback' => function (WP_REST_Request $request) {
                return gaia_dashboard_proxy_json($request, '/v1/profile/preferences', [], 'PUT');
            },
        ],
    ]);

    register_rest_route('gaia/v1', '/member/guide-seen', [
        [
            'methods' => WP_REST_Server::CREATABLE,
            'permission_callback' => '__return_true',
            'callback' => function (WP_REST_Request $request) {
                return gaia_dashboard_proxy_json($request, '/v1/profile/guide/seen', [], 'POST');
            },
        ],
    ]);

    register_rest_route('gaia/v1', '/member/notifications', [
        [
            'methods' => WP_REST_Server::READABLE,
            'permission_callback' => '__return_true',
            'callback' => function (WP_REST_Request $request) {
                return gaia_dashboard_proxy_json($request, '/v1/profile/notifications');
            },
        ],
        [
            'methods' => WP_REST_Server::EDITABLE,
            'permission_callback' => '__return_true',
            'callback' => function (WP_REST_Request $request) {
                return gaia_dashboard_proxy_json($request, '/v1/profile/notifications', [], WP_REST_Server::EDITABLE);
            },
        ],
    ]);

    register_rest_route('gaia/v1', '/member/account', [
        [
            'methods' => WP_REST_Server::DELETABLE,
            'permission_callback' => '__return_true',
            'callback' => function (WP_REST_Request $request) {
                return gaia_dashboard_proxy_json($request, '/v1/profile/account', [], 'DELETE');
            },
        ],
    ]);

    register_rest_route('gaia/v1', '/member/account/preflight', [
        [
            'methods' => WP_REST_Server::READABLE,
            'permission_callback' => '__return_true',
            'callback' => function (WP_REST_Request $request) {
                return gaia_dashboard_proxy_json($request, '/v1/profile/account/preflight');
            },
        ],
    ]);

    register_rest_route('gaia/v1', '/internal/bug-report-alert', [
        [
            'methods' => WP_REST_Server::CREATABLE,
            'permission_callback' => 'gaia_bug_report_alert_permission',
            'callback' => 'gaia_bug_report_alert_callback',
        ],
    ]);
});

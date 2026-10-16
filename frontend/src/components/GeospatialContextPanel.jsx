import { useEffect, useState, useRef } from 'react';
import {
  Car,
  Cloud,
  CloudRain,
  Compass,
  Layers,
  LoaderCircle,
  Shield,
  Sparkles,
  Thermometer,
  Wind,
} from 'lucide-react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { getCaseGeospatialContext } from '../services/geospatialApi';

export function GeospatialContextPanel({ referenceId, initialLocation, isStaff = false }) {
  const [geoData, setGeoData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const miniMapContainerRef = useRef(null);
  const miniMapObjRef = useRef(null);

  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    setError(null);

    getCaseGeospatialContext(referenceId)
      .then((res) => {
        if (!isMounted) return;
        setGeoData(res);
        setLoading(false);
      })
      .catch((err) => {
        if (!isMounted) return;
        setError(err?.message || 'Geospatial intelligence context is unavailable.');
        setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [referenceId]);

  const hasCoords = Boolean(
    (geoData?.location?.latitude && geoData?.location?.longitude) ||
    (initialLocation?.latitude && initialLocation?.longitude)
  );

  const lat = geoData?.location?.latitude || initialLocation?.latitude;
  const lng = geoData?.location?.longitude || initialLocation?.longitude;

  useEffect(() => {
    if (!hasCoords || !miniMapContainerRef.current || loading || error) return;

    if (!miniMapObjRef.current) {
      try {
        const map = L.map(miniMapContainerRef.current, {
          zoomControl: false,
          attributionControl: false,
          scrollWheelZoom: false,
        }).setView([lat, lng], 15);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
          maxZoom: 19,
        }).addTo(map);

        // Marker for target case
        const targetIcon = L.divIcon({
          className: 'target-case-marker',
          html: '<div class="target-marker-dot"></div>',
          iconSize: [20, 20],
          iconAnchor: [10, 10],
        });
        L.marker([lat, lng], { icon: targetIcon })
          .addTo(map)
          .bindPopup(`<strong>Target Incident</strong><br/>${geoData?.road?.road_name || 'Reported Location'}`);

        // Draw 250m search radius
        L.circle([lat, lng], {
          radius: geoData?.nearby_cases?.radius_meters || 250,
          color: '#164b3a',
          fillColor: '#164b3a',
          fillOpacity: 0.08,
          weight: 1.5,
          dashArray: '3, 4',
        }).addTo(map);

        miniMapObjRef.current = map;
      } catch (err) {
        console.warn('MiniMap initialization notice:', err);
      }
    }

    return () => {
      if (miniMapObjRef.current) {
        miniMapObjRef.current.remove();
        miniMapObjRef.current = null;
      }
    };
  }, [hasCoords, lat, lng, loading, error, geoData]);

  if (loading) {
    return (
      <div className="detail-section geospatial-panel-loading">
        <LoaderCircle size={18} className="spin-slow" />
        <span>Evaluating geospatial intelligence and civic context...</span>
      </div>
    );
  }

  if (error || !geoData) {
    return (
      <div className="detail-section">
        <h4>Geospatial Civic Intelligence</h4>
        <p className="text-muted" style={{ fontSize: '12px' }}>
          {error || 'Geospatial context is currently unavailable for this record.'}
        </p>
      </div>
    );
  }

  const quality = geoData.location_match || 'approximate';
  const sourceStatus = geoData.source_status || 'live';
  const nearby = geoData.nearby_cases || { count: 0, unresolved_count: 0 };
  const road = geoData.road || {};
  const segment = geoData.road_segment || {};
  const ext = geoData.external_context;
  const weather = ext?.weather;
  const rainfall = ext?.rainfall;
  const traffic = ext?.traffic;
  const correlation = ext?.environmental_correlation;

  return (
    <div className="detail-section geospatial-context-card">
      <div className="geo-header-row">
        <h4>
          <Compass size={16} /> Advanced Geospatial Intelligence
        </h4>
        <div className="geo-badges-group">
          <span className={`geo-quality-pill quality-${quality}`} title="Location matching quality based on evidence">
            {quality.toUpperCase()} MATCH
          </span>
          <span className={`geo-source-pill source-${sourceStatus}`} title="Geocoding source freshness state">
            {sourceStatus.toUpperCase()}
          </span>
        </div>
      </div>

      <div className="geo-body-grid">
        <div className="geo-info-column">
          <div className="geo-metric-row">
            <span className="geo-metric-key">Identified Road:</span>
            <span className="geo-metric-val">
              <strong>{road.road_name || 'Unnamed / Unresolved Street'}</strong>
              {road.road_reference && <span className="geo-ref-tag">{road.road_reference}</span>}
            </span>
          </div>

          <div className="geo-metric-row">
            <span className="geo-metric-key">Road Classification:</span>
            <span className="geo-metric-val">
              <span className="geo-type-pill">
                {(road.road_type || 'unknown').replaceAll('_', ' ')}
              </span>
            </span>
          </div>

          {segment.start_end_context && (
            <div className="geo-metric-row">
              <span className="geo-metric-key">Road Context:</span>
              <span className="geo-metric-val text-muted">{segment.start_end_context}</span>
            </div>
          )}

          {geoData.location?.accuracy_m !== null && geoData.location?.accuracy_m !== undefined && (
            <div className="geo-metric-row">
              <span className="geo-metric-key">GPS Accuracy:</span>
              <span className="geo-metric-val">
                ±{Math.round(geoData.location.accuracy_m)}m
                <small className="text-muted"> ({geoData.location.accuracy_m <= 25 ? 'High precision' : 'Approximate precision'})</small>
              </span>
            </div>
          )}

          <div className="geo-metric-row">
            <span className="geo-metric-key">Jurisdiction:</span>
            <span className="geo-metric-val">
              {geoData.jurisdiction?.name || 'Local Administrative Area'}
            </span>
          </div>

          <div className="geo-metric-row">
            <span className="geo-metric-key">Nearby Incidents:</span>
            <span className="geo-metric-val">
              <strong>{nearby.count} reported</strong> within {nearby.radius_meters || 250}m
              {nearby.unresolved_count > 0 && (
                <span className="geo-unresolved-flag"> ({nearby.unresolved_count} unresolved)</span>
              )}
            </span>
          </div>

          {nearby.recurrence_count > 0 && (
            <div className="geo-alert-row recurrence">
              <Sparkles size={14} />
              <span>{nearby.recurrence_count} historical recurrence candidate(s) within duplicate/recurrence window.</span>
            </div>
          )}

          {nearby.hotspot_candidate && (
            <div className="geo-alert-row hotspot">
              <Layers size={14} />
              <span>Local reporting concentration detected along this road corridor.</span>
            </div>
          )}

          {isStaff && geoData.authority_preview && (
            <div className="geo-staff-box">
              <span className="geo-staff-title"><Shield size={13} /> Official Authority Attribution</span>
              <p style={{ margin: '4px 0 0', fontSize: '11px' }}>
                Status: <strong>{geoData.authority_preview.authority_status}</strong>
                {geoData.authority_preview.maintenance_authority?.name && ` (${geoData.authority_preview.maintenance_authority.name})`}
              </p>
            </div>
          )}
        </div>

        {hasCoords && (
          <div className="geo-minimap-column">
            <div ref={miniMapContainerRef} className="geo-minimap-container" />
            <span className="geo-minimap-caption">
              📍 Incident location &amp; {nearby.radius_meters || 250}m civic radius
            </span>
          </div>
        )}
      </div>

      {ext && (
        <div className="geo-external-section">
          <div className="geo-external-header">
            <h5>
              <CloudRain size={15} /> Environmental &amp; External Context
            </h5>
            <span className={`geo-source-pill source-${ext.status || 'live'}`}>
              {(ext.status || 'live').toUpperCase()}
            </span>
          </div>

          <div className="geo-external-cards">
            {rainfall && rainfall.status !== 'unavailable' && (
              <div className="geo-ext-card">
                <div className="geo-ext-card-icon rain">
                  <CloudRain size={16} />
                </div>
                <div className="geo-ext-card-body">
                  <span className="geo-ext-card-label">Rainfall ({rainfall.window_hours}h)</span>
                  <span className="geo-ext-card-val">
                    {rainfall.rainfall_mm !== null && rainfall.rainfall_mm !== undefined
                      ? `${rainfall.rainfall_mm} mm`
                      : '0.0 mm'}
                    <span className={`intensity-badge ${rainfall.intensity || 'none'}`}>
                      {(rainfall.intensity || 'none').toUpperCase()}
                    </span>
                  </span>
                </div>
              </div>
            )}

            {weather && weather.status !== 'unavailable' && (
              <>
                <div className="geo-ext-card">
                  <div className="geo-ext-card-icon temp">
                    <Thermometer size={16} />
                  </div>
                  <div className="geo-ext-card-body">
                    <span className="geo-ext-card-label">Temperature</span>
                    <span className="geo-ext-card-val">
                      {weather.temperature_c !== null && weather.temperature_c !== undefined
                        ? `${weather.temperature_c}°C`
                        : 'N/A'}
                    </span>
                  </div>
                </div>

                <div className="geo-ext-card">
                  <div className="geo-ext-card-icon wind">
                    <Wind size={16} />
                  </div>
                  <div className="geo-ext-card-body">
                    <span className="geo-ext-card-label">Wind Speed</span>
                    <span className="geo-ext-card-val">
                      {weather.wind_speed_mps !== null && weather.wind_speed_mps !== undefined
                        ? `${weather.wind_speed_mps} m/s`
                        : 'N/A'}
                    </span>
                  </div>
                </div>

                {weather.condition && (
                  <div className="geo-ext-card">
                    <div className="geo-ext-card-icon cloud">
                      <Cloud size={16} />
                    </div>
                    <div className="geo-ext-card-body">
                      <span className="geo-ext-card-label">Weather</span>
                      <span className="geo-ext-card-val">{weather.condition}</span>
                    </div>
                  </div>
                )}
              </>
            )}

            {traffic && traffic.status !== 'not_configured' && traffic.status !== 'unavailable' && (
              <div className="geo-ext-card">
                <div className="geo-ext-card-icon traffic">
                  <Car size={16} />
                </div>
                <div className="geo-ext-card-body">
                  <span className="geo-ext-card-label">Traffic Condition</span>
                  <span className="geo-ext-card-val">{traffic.traffic_condition || 'Normal'}</span>
                </div>
              </div>
            )}
          </div>

          {correlation && (
            <div className={`geo-alert-row ${correlation.correlation_observed ? 'recurrence' : 'hotspot'}`} style={{ marginTop: '8px' }}>
              <Sparkles size={14} />
              <span>{correlation.correlation_summary}</span>
            </div>
          )}

          <div className="geo-ext-provenance">
            <small className="text-muted">
              Source: {weather?.source || 'Open-Meteo'} • Freshness: {ext.status} • {correlation?.causal_disclaimer || 'External environmental correlation is contextual and does not establish causation.'}
            </small>
          </div>
        </div>
      )}

      <div className="geo-footer-notice">
        <small className="text-muted">
          Evidence-driven geospatial intelligence: Proximity indicates reporting clustering and does not prove that reports share an identical physical defect.
        </small>
      </div>
    </div>
  );
}

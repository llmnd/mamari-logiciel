"use client";

import { useEffect, useRef } from "react";
import type { Map as LeafletMap, Marker } from "leaflet";

export interface DeliveryMapPoint {
  latitude: number;
  longitude: number;
}

export function DeliveryMap({
  location,
  onSelect,
}: {
  location: DeliveryMapPoint | null;
  onSelect: (point: DeliveryMapPoint) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const markerRef = useRef<Marker | null>(null);
  const onSelectRef = useRef(onSelect);
  const locationRef = useRef(location);

  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  useEffect(() => {
    locationRef.current = location;
  }, [location]);

  useEffect(() => {
    let disposed = false;
    let map: LeafletMap | null = null;

    async function initializeMap() {
      const leaflet = await import("leaflet");
      if (disposed || !containerRef.current) return;

      map = leaflet.map(containerRef.current, {
        scrollWheelZoom: false,
      }).setView([12.1348, 15.0557], 13);
      leaflet
        .tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 19,
          attribution:
            '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        })
        .addTo(map);
      mapRef.current = map;

      function placeMarker(point: DeliveryMapPoint) {
        if (!map) return;
        const coordinates: [number, number] = [point.latitude, point.longitude];
        if (markerRef.current) {
          markerRef.current.setLatLng(coordinates);
        } else {
          markerRef.current = leaflet.marker(coordinates, {
            draggable: true,
            icon: leaflet.divIcon({
              className: "delivery-map-pin",
              html: "<span></span>",
              iconSize: [28, 28],
              iconAnchor: [14, 14],
            }),
          }).addTo(map);
          markerRef.current.on("dragend", () => {
            const position = markerRef.current?.getLatLng();
            if (position) {
              onSelectRef.current({
                latitude: position.lat,
                longitude: position.lng,
              });
            }
          });
        }
        map.setView(coordinates, Math.max(map.getZoom(), 16));
      }

      map.on("click", (event) => {
        const point = {
          latitude: event.latlng.lat,
          longitude: event.latlng.lng,
        };
        placeMarker(point);
        onSelectRef.current({
          ...point,
        });
      });

      const initialLocation = locationRef.current;
      if (initialLocation) placeMarker(initialLocation);
    }

    void initializeMap();
    return () => {
      disposed = true;
      map?.remove();
      mapRef.current = null;
      markerRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (!location) {
      markerRef.current?.remove();
      markerRef.current = null;
      return;
    }
    const coordinates: [number, number] = [location.latitude, location.longitude];
    if (markerRef.current) {
      markerRef.current.setLatLng(coordinates);
    } else {
      void import("leaflet").then((leaflet) => {
        const currentMap = mapRef.current;
        if (!currentMap || !containerRef.current || markerRef.current) return;
        const currentLocation = locationRef.current;
        if (!currentLocation) return;
        const currentCoordinates: [number, number] = [
          currentLocation.latitude,
          currentLocation.longitude,
        ];
        markerRef.current = leaflet.marker(currentCoordinates, {
          draggable: true,
          icon: leaflet.divIcon({
            className: "delivery-map-pin",
            html: "<span></span>",
            iconSize: [28, 28],
            iconAnchor: [14, 14],
          }),
        }).addTo(currentMap);
        markerRef.current.on("dragend", () => {
          const position = markerRef.current?.getLatLng();
          if (position) {
            onSelectRef.current({
              latitude: position.lat,
              longitude: position.lng,
            });
          }
        });
        currentMap.setView(currentCoordinates, Math.max(currentMap.getZoom(), 16));
      });
    }
    map.setView(coordinates, Math.max(map.getZoom(), 16));
  }, [location]);

  return <div className="delivery-map" ref={containerRef} aria-label="Carte pour choisir le point de livraison" />;
}

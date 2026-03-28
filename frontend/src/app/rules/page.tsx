"use client";
import React, { useEffect, useState } from 'react';

export default function RulesRegistryPage() {
  return (
    <div className="p-8">
      <div className="bg-blue-50 border-l-4 border-blue-500 p-4 mb-8">
        <p className="text-blue-700">
          <strong>Shared Cloud Registry:</strong> This registry is shared across all sessions. Rules shown here were contributed by all uploaded documents.
        </p>
      </div>
      <h1 className="text-2xl font-bold mb-4">Rules Registry</h1>
      <p className="text-gray-600 mb-8">All active rules extracted from RBI documents. Last updated: Just now.</p>
      <div className="flex gap-4 mb-4">
        <span className="badge bg-green-100 text-green-800 px-2 py-1 rounded">25 NEW</span>
        <span className="badge bg-blue-100 text-blue-800 px-2 py-1 rounded">30 EXISTING</span>
        <span className="badge bg-yellow-100 text-yellow-800 px-2 py-1 rounded">5 MODIFIED</span>
        <span className="badge bg-gray-100 text-gray-800 px-2 py-1 rounded">0 SUPERSEDED</span>
      </div>
      <table className="min-w-full bg-white border border-gray-200">
        <thead>
          <tr>
            <th className="py-2 px-4 border-b text-left">Rule</th>
            <th className="py-2 px-4 border-b text-left">Provenance</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td className="py-2 px-4 border-b">Sample Rule 1</td>
            <td className="py-2 px-4 border-b">
              <span className="text-xs bg-gray-100 rounded px-2 py-1">From: Master Direction 2025</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
